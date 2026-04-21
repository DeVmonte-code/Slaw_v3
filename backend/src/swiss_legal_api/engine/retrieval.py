from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from ..schemas import Citation
from ..seeding.embedder import embed_query


@dataclass
class RetrievedChunk:
    text: str
    score: float


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def retrieve_for_citation(citation: Citation, extra_query: str) -> list[RetrievedChunk]:
    vec = embed_query(f"{citation.article} {extra_query}")
    client = _client()
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vec,
        limit=3,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="sr_number", match=qmodels.MatchValue(value=citation.sr_number),
                ),
                qmodels.FieldCondition(
                    key="article", match=qmodels.MatchValue(value=citation.article),
                ),
            ]
        ),
        with_payload=True,
    )
    return [
        RetrievedChunk(text=(r.payload or {}).get("text", ""), score=r.score)
        for r in response.points
    ]
