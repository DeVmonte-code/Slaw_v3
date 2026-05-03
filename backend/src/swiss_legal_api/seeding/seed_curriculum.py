"""Curriculum (doctrinal-PDF) seeder for the second Qdrant collection.

Walks ``backend/seed/curriculum/*.pdf``, extracts text, chunks each PDF
sentence-aware, and upserts into the ``co_curriculum`` collection with
stable UUID5 IDs derived from ``(source_doc, page, chunk_index)``.

Optional sidecar metadata: alongside each ``foo.pdf`` contributors may
drop a ``foo.meta.json``::

    {
      "language": "en",
      "topic_tags": ["contracts", "errors"],
      "chapter_index": { "1": "Chapter 1: Formation",
                         "12": "Chapter 2: Errors" }
    }

The chapter index is sparse — it lists the *first* page of each chapter
and chunks inherit the most recent earlier entry; absent chapters become
None and the UI falls back to "page N".

The seeder is intentionally a no-op when ``seed/curriculum/`` is empty so
the bootstrap deployment (no PDFs committed yet) doesn't fail.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from .curriculum_chunker import (
    CurriculumChunk,
    chunk_pages,
    extract_pdf_pages,
)
from .embedder import embed_passage

# Distinct namespace from law-article IDs so a curriculum chunk and a law
# article that happen to share a key string can never collide on UUID5.
_ID_NAMESPACE = uuid.UUID("3a4f7c2e-9b8d-5c1a-bb2f-7a4d3c8e1f9b")


def _stable_id(chunk: CurriculumChunk) -> str:
    """``uuid5(NAMESPACE, "{source_doc}|{page}|{chunk_index}")`` — re-runs
    upsert in place rather than churning IDs. Bumping the namespace would
    invalidate every existing point, so keep it constant across releases."""
    key = f"{chunk.source_doc}|{chunk.page}|{chunk.chunk_index}"
    return str(uuid.uuid5(_ID_NAMESPACE, key))


def _load_sidecar(pdf_path: Path) -> dict[str, Any]:
    """Read ``<stem>.meta.json`` if present. Missing file → empty dict
    (everything defaults). Malformed JSON raises so a typo'd sidecar
    fails loud at ingest time, not at query time."""
    sidecar = pdf_path.with_suffix(".meta.json")
    if not sidecar.exists():
        return {}
    return dict(json.loads(sidecar.read_text()))


def _build_chapter_index(raw: Any) -> dict[int, str]:
    """Normalise sidecar ``chapter_index`` (string keys in JSON) into a
    sparse ``{first_page: chapter_label}`` map applied at chunk time.
    Forward-fills inside ``chunk_pages`` are handled by passing the dict
    directly — the chunker reads it page-by-page and inherits the most
    recent earlier entry naturally."""
    if not raw:
        return {}
    out: dict[int, str] = {}
    for k, v in dict(raw).items():
        out[int(k)] = str(v)
    return out


def _resolve_chapter_for_page(page: int, chapter_index: dict[int, str]) -> str | None:
    """Forward-fill chapter labels: a page inherits the most recent earlier
    chapter entry. Used when the sidecar is sparse (one entry per chapter
    boundary, not per page)."""
    if not chapter_index:
        return None
    candidates = [k for k in chapter_index if k <= page]
    if not candidates:
        return None
    return chapter_index[max(candidates)]


def _expand_chapter_index(chapter_index: dict[int, str], total_pages: int) -> dict[int, str]:
    """Forward-fill a sparse chapter_index over [1..total_pages]."""
    if not chapter_index or total_pages <= 0:
        return {}
    out: dict[int, str] = {}
    for page in range(1, total_pages + 1):
        ch = _resolve_chapter_for_page(page, chapter_index)
        if ch is not None:
            out[page] = ch
    return out


def ingest_pdf(pdf_path: Path) -> list[CurriculumChunk]:
    """End-to-end PDF → chunk pipeline. Pulled out of ``main`` so tests
    can monkey-patch ``extract_pdf_pages`` without spinning up Qdrant.

    The ``source_doc`` is the filename stem (e.g. ``co_articles_1_183``);
    contributors should pick stable, human-readable names because the stem
    is part of the UUID5 ID — renaming a PDF orphans its existing points
    until reconciliation runs.
    """
    sidecar = _load_sidecar(pdf_path)
    pages = extract_pdf_pages(pdf_path)
    chapter_index = _build_chapter_index(sidecar.get("chapter_index"))
    section_index = _build_chapter_index(sidecar.get("section_index"))
    expanded_chapters = _expand_chapter_index(chapter_index, len(pages))
    expanded_sections = _expand_chapter_index(section_index, len(pages))
    return chunk_pages(
        source_doc=pdf_path.stem,
        pages=pages,
        language=str(sidecar.get("language", "en")),
        topic_tags=tuple(sidecar.get("topic_tags") or ()),
        chapter_index=expanded_chapters,
        section_index=expanded_sections,
    )


def _ensure_collection(client: QdrantClient, name: str) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE),
        )
    # Keyword payload indexes that ``retrieve_supporting_context`` filters
    # against. Wrapped in suppress so re-runs on an already-indexed
    # collection are no-ops.
    for field_name in ("source_doc", "topic_tags", "language"):
        with contextlib.suppress(Exception):
            client.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )


def _upsert_chunks(client: QdrantClient, collection: str, chunks: list[CurriculumChunk]) -> None:
    points: list[qmodels.PointStruct] = []
    for c in chunks:
        vec = embed_passage(c.text)
        points.append(
            qmodels.PointStruct(
                id=_stable_id(c),
                vector=vec,
                payload={
                    "source_doc": c.source_doc,
                    "page": c.page,
                    "chunk_index": c.chunk_index,
                    "chapter": c.chapter,
                    "section": c.section,
                    "language": c.language,
                    # Qdrant's KEYWORD index supports list fields natively
                    # so MatchAny topic-tag filters work on the array.
                    "topic_tags": list(c.topic_tags),
                    "text": c.text,
                },
            )
        )
    BATCH = 256
    for start in range(0, len(points), BATCH):
        client.upsert(
            collection_name=collection,
            points=points[start : start + BATCH],
            wait=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m swiss_legal_api.seeding.seed_curriculum",
        description=(
            "Seed the curriculum (doctrinal-PDF) Qdrant collection from "
            "the seed/curriculum/ directory."
        ),
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        help=(
            "Directory containing PDFs to ingest. Defaults to "
            "backend/seed/curriculum/ relative to the package root."
        ),
    )
    args = parser.parse_args(argv)

    # QDRANT_URL is required (we have to know where to write); QDRANT_API_KEY
    # is optional so the seeder works against unauthenticated/local Qdrant
    # (e.g. `docker run qdrant/qdrant` on a developer's laptop) — the
    # client treats api_key=None as "no auth header".
    if not settings.qdrant_url:
        print("QDRANT_URL required", file=sys.stderr)
        return 1

    if args.source_dir:
        source_dir = Path(args.source_dir)
    else:
        source_dir = Path(__file__).resolve().parents[3] / "seed" / "curriculum"

    if not source_dir.exists():
        print(
            f"curriculum source dir {source_dir} does not exist; "
            "creating it as an empty placeholder"
        )
        source_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        print(
            f"No PDFs found under {source_dir}; nothing to seed. Drop "
            "doctrinal PDFs there and re-run."
        )
        return 0

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    _ensure_collection(client, settings.curriculum_collection)

    total = 0
    for pdf in pdfs:
        chunks = ingest_pdf(pdf)
        if not chunks:
            print(f"  {pdf.name}: 0 chunks (extracted no text — scanned PDF?)")
            continue
        _upsert_chunks(client, settings.curriculum_collection, chunks)
        total += len(chunks)
        print(f"  {pdf.name}: {len(chunks)} chunks")
    print(
        f"Seeded {total} curriculum chunks across {len(pdfs)} source docs "
        f"into {settings.curriculum_collection}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
