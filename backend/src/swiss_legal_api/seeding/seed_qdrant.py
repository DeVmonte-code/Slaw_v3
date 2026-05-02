from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from .embedder import embed_passage


def _normalize_date(value: Any) -> str | None:
    """Coerce an effective/repealed date to RFC3339 datetime at midnight UTC.

    Accepts 'YYYY-MM-DD' or full ISO datetimes; returns None when the input
    is None or an empty string. Unknown shapes raise ValueError so the
    seeder fails loud on bad data.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"date must be a string, got {type(value).__name__}")
    s = value.strip()
    if not s:
        return None
    if "T" in s:
        return s if s.endswith("Z") else s + "Z"
    # Validates 'YYYY-MM-DD'.
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        raise ValueError(f"date must be 'YYYY-MM-DD' or ISO datetime, got {s!r}")
    return f"{s}T00:00:00Z"


def main() -> int:
    if not settings.qdrant_url or not settings.qdrant_api_key:
        print("QDRANT_URL and QDRANT_API_KEY required", file=sys.stderr)
        return 1

    seed = Path(__file__).resolve().parents[3] / "seed" / "law_articles.json"
    articles = json.loads(seed.read_text())

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
                f"law_articles.json entry #{i} ({a.get('sr_number')} "
                f"Art. {a.get('article')}) is missing effective_date"
            )
        vec = embed_passage(a["text"])
        points.append(qmodels.PointStruct(id=i, vector=vec, payload=payload))

    client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
        wait=True,
    )
    print(f"Seeded {len(points)} articles into {settings.qdrant_collection}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
