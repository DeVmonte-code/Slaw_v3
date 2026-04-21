from __future__ import annotations

from functools import lru_cache
from typing import cast

from sentence_transformers import SentenceTransformer

from ..config import settings


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    return cast(SentenceTransformer, SentenceTransformer(settings.embedding_model))


def embed_passage(text: str) -> list[float]:
    model = get_embedder()
    vec = model.encode(f"passage: {text}", normalize_embeddings=True)
    return cast(list[float], vec.tolist())


def embed_query(text: str) -> list[float]:
    model = get_embedder()
    vec = model.encode(f"query: {text}", normalize_embeddings=True)
    return cast(list[float], vec.tolist())
