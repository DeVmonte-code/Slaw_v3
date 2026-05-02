from __future__ import annotations

import argparse
import contextlib
import json
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from .embedder import embed_passage

# Stable namespace for UUID5 derivation. Bumping this would invalidate every
# existing point ID, so keep it constant across releases.
_ID_NAMESPACE = uuid.UUID("c0a801f4-5e2c-4f9f-9d6a-7f0b4d1e8a30")


def _normalize_date(value: Any) -> str | None:
    """Coerce an effective/repealed date to RFC3339 datetime at midnight UTC.

    Accepts:
      * None or empty string → returns None.
      * 'YYYY-MM-DD' → midnight UTC.
      * Full ISO datetimes including 'Z' or '+HH:MM' offsets → converted to UTC.

    Unknown shapes raise ValueError so the seeder fails loud on bad data.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"date must be a string, got {type(value).__name__}")
    s = value.strip()
    if not s:
        return None
    if "T" in s:
        # datetime.fromisoformat understands '+HH:MM' offsets natively;
        # 'Z' is accepted in Python 3.11+. Convert to UTC, then emit RFC3339.
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid ISO datetime: {s!r}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Validates 'YYYY-MM-DD'. date.fromisoformat() rejects malformed inputs
    # (wrong length, bad separators, impossible months/days) for us.
    try:
        date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(
            f"date must be 'YYYY-MM-DD' or ISO datetime, got {s!r}"
        ) from exc
    return f"{s}T00:00:00Z"


def _stable_id(article: dict[str, Any]) -> str:
    """Derive a deterministic Qdrant point ID for an article record.

    Idempotency contract: two re-runs of the seeder over the same logical
    record (same eli_uri + article + paragraph + language) produce the same
    UUID, so we upsert in place rather than churning the collection.

    Manual records (no ``eli_uri``) are namespaced under ``manual:`` so that
    a future Fedlex-derived record for the same SR/article does not collide
    with the placeholder it replaces — they have different eli_uris.
    """
    eli = article.get("eli_uri")
    if eli:
        key = f"{eli}|{article['article']}|{article.get('paragraph', '1')}|{article['language']}"
    else:
        key = (
            f"manual:{article['sr_number']}|{article['article']}"
            f"|{article.get('paragraph', '1')}|{article['language']}"
        )
    return str(uuid.uuid5(_ID_NAMESPACE, key))


def _coverage_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    """Tuple identifying a logical (sr, article, paragraph, language) row.

    Used to merge the Fedlex snapshot with the manual bootstrap: any manual
    row whose key is *not* covered by Fedlex still gets seeded so acts that
    Fedlex doesn't publish as AN-XML (e.g. SR 141.0) keep flowing into the
    corpus from the hand-pasted source.
    """
    return (
        str(record.get("sr_number", "")),
        str(record.get("article", "")),
        str(record.get("paragraph", "1")),
        str(record.get("language", "")),
    )


def _load_articles(explicit: str | None) -> tuple[list[dict[str, Any]], list[Path]]:
    """Resolve and load article records, merging Fedlex + manual when both
    exist.

    Behavior:
      * ``--source X`` → load only X (used for tests and explicit pinning).
      * Both ``law_articles.fedlex.json`` and ``law_articles.json`` exist →
        load Fedlex, then layer manual rows on top *only for keys Fedlex
        doesn't cover*. Fedlex always wins on collision so a refreshed
        snapshot supersedes the bootstrap text for the same article.
      * Only the manual file exists → load it (bootstrap mode).
      * Neither file exists → caller raises.

    Returns (records, source_paths) so the CLI can log which files actually
    contributed.
    """
    if explicit:
        return json.loads(Path(explicit).read_text()), [Path(explicit)]

    seed_dir = Path(__file__).resolve().parents[3] / "seed"
    fedlex = seed_dir / "law_articles.fedlex.json"
    manual = seed_dir / "law_articles.json"

    if not fedlex.exists():
        return json.loads(manual.read_text()), [manual]

    fedlex_records: list[dict[str, Any]] = json.loads(fedlex.read_text())
    if not manual.exists():
        return fedlex_records, [fedlex]

    covered = {_coverage_key(r) for r in fedlex_records}
    manual_records: list[dict[str, Any]] = json.loads(manual.read_text())
    fallback = [r for r in manual_records if _coverage_key(r) not in covered]
    return fedlex_records + fallback, [fedlex, manual]


def _reconcile_stale_points(
    client: QdrantClient, collection: str, fresh_ids: set[str]
) -> int:
    """Delete points whose IDs are not in ``fresh_ids``.

    Two reasons this matters:
      1. The pre-Task-#19 seeder used integer IDs (``1..N``); after the
         switchover those legacy points would otherwise linger forever
         because UUID5 IDs never collide with integers, polluting retrieval
         with stale paragraph text.
      2. Future Fedlex snapshots may *shrink* the corpus (repeals, eId
         renumbering). Without reconciliation the dropped articles would
         still surface in search results.

    We scroll the entire collection (small enough — single five-digit
    article count) and delete any IDs not present in the fresh upsert set.
    """
    stale: list[Any] = []
    next_offset: Any = None
    while True:
        records, next_offset = client.scroll(
            collection_name=collection,
            limit=1024,
            with_payload=False,
            with_vectors=False,
            offset=next_offset,
        )
        for rec in records:
            if str(rec.id) not in fresh_ids:
                stale.append(rec.id)
        if next_offset is None:
            break
    if stale:
        BATCH = 256
        for start in range(0, len(stale), BATCH):
            client.delete(
                collection_name=collection,
                points_selector=qmodels.PointIdsList(points=stale[start:start + BATCH]),
                wait=True,
            )
    return len(stale)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m swiss_legal_api.seeding.seed_qdrant",
        description="Seed the Qdrant law-articles collection.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Path to a JSON list of article records. Defaults to merging "
            "seed/law_articles.fedlex.json (if present) with the manual "
            "seed/law_articles.json fallback for keys Fedlex doesn't cover."
        ),
    )
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        help=(
            "Skip the post-upsert pass that deletes points whose IDs are no "
            "longer in the fresh seed (used to clear pre-UUID5 legacy IDs "
            "and articles dropped by a fresh Fedlex snapshot). Pass this "
            "flag in incremental seeding scenarios where you intentionally "
            "want stale points to remain."
        ),
    )
    args = parser.parse_args(argv)

    if not settings.qdrant_url or not settings.qdrant_api_key:
        print("QDRANT_URL and QDRANT_API_KEY required", file=sys.stderr)
        return 1

    try:
        articles, source_paths = _load_articles(args.source)
    except FileNotFoundError as exc:
        print(f"seed file missing: {exc}", file=sys.stderr)
        return 1
    sources_repr = " + ".join(str(p) for p in source_paths)
    print(f"Loading {len(articles)} articles from {sources_repr}")

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE),
        )

    # Keyword payload indexes (exact-match filters used by retrieval).
    for field in ("sr_number", "article", "language", "canton"):
        with contextlib.suppress(Exception):
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )

    # Datetime payload indexes (range filters for not-yet-effective and
    # repealed-law gates). Wrapped in suppress so a re-run on an already
    # indexed collection is a no-op.
    for field in ("effective_date", "repealed_date"):
        with contextlib.suppress(Exception):
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.DATETIME,
            )

    points: list[qmodels.PointStruct] = []
    for i, a in enumerate(articles, start=1):
        # Default to federal jurisdiction if seed entry omits canton.
        payload: dict[str, Any] = {**a, "canton": a.get("canton", "CH")}
        payload["effective_date"] = _normalize_date(payload.get("effective_date"))
        payload["repealed_date"] = _normalize_date(payload.get("repealed_date"))
        if payload["effective_date"] is None:
            raise ValueError(
                f"{sources_repr} entry #{i} ({a.get('sr_number')} "
                f"Art. {a.get('article')}) is missing effective_date"
            )
        vec = embed_passage(a["text"])
        points.append(
            qmodels.PointStruct(
                id=_stable_id(a),
                vector=vec,
                payload=payload,
            )
        )

    # Batch the upsert so re-seeding a multi-thousand-article corpus doesn't
    # ship one giant request that can exceed Qdrant Cloud's body-size limits.
    BATCH = 256
    for start in range(0, len(points), BATCH):
        client.upsert(
            collection_name=settings.qdrant_collection,
            points=points[start:start + BATCH],
            wait=True,
        )
    print(f"Seeded {len(points)} articles into {settings.qdrant_collection}")

    if not args.no_reconcile:
        fresh_ids = {str(p.id) for p in points}
        deleted = _reconcile_stale_points(
            client, settings.qdrant_collection, fresh_ids
        )
        if deleted:
            print(f"Reconciled {deleted} stale points (legacy IDs / dropped articles)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
