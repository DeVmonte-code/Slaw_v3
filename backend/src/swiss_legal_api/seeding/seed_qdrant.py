from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from .embedder import embed_passage


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

    for field in ("sr_number", "article", "language"):
        with contextlib.suppress(Exception):
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )

    points: list[qmodels.PointStruct] = []
    for i, a in enumerate(articles, start=1):
        vec = embed_passage(a["text"])
        points.append(qmodels.PointStruct(id=i, vector=vec, payload=a))

    client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
        wait=True,
    )
    print(f"Seeded {len(points)} articles into {settings.qdrant_collection}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
