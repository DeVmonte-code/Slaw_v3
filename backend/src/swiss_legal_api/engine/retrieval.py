from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from ..schemas import Citation
from ..seeding.embedder import embed_query

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    score: float
    language: str = "de"
    effective_date: date | None = None


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def _today_utc() -> date:
    return datetime.now(UTC).date()


def _to_dt_utc(d: date) -> datetime:
    """Promote a date to a UTC datetime at midnight for Qdrant range filters."""
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _build_query_filter(
    citation: Citation, profile_canton: str, today: date
) -> qmodels.Filter:
    """Build the Qdrant filter that gates retrieval on the four guardrails:

    - sr_number match (exact)
    - article match (exact)
    - canton ∈ {profile_canton, "CH"} (federal law applies in every canton)
    - effective_date <= today (no not-yet-in-force law)
    - repealed_date IS NULL OR > today (no repealed law)
    """
    today_dt = _to_dt_utc(today)
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="sr_number",
                match=qmodels.MatchValue(value=citation.sr_number),
            ),
            qmodels.FieldCondition(
                key="article",
                match=qmodels.MatchValue(value=citation.article),
            ),
            qmodels.FieldCondition(
                key="canton",
                match=qmodels.MatchAny(any=[profile_canton, "CH"]),
            ),
            qmodels.FieldCondition(
                key="effective_date",
                range=qmodels.DatetimeRange(lte=today_dt),
            ),
            qmodels.Filter(
                should=[
                    qmodels.IsEmptyCondition(
                        is_empty=qmodels.PayloadField(key="repealed_date"),
                    ),
                    qmodels.IsNullCondition(
                        is_null=qmodels.PayloadField(key="repealed_date"),
                    ),
                    qmodels.FieldCondition(
                        key="repealed_date",
                        range=qmodels.DatetimeRange(gt=today_dt),
                    ),
                ],
            ),
        ],
    )


def retrieve_for_citation(
    citation: Citation,
    extra_query: str,
    profile_canton: str = "CH",
    score_threshold: float | None = None,
    today: date | None = None,
    caller_context: str = "",
) -> list[RetrievedChunk]:
    """Return chunks above `score_threshold` that satisfy the guardrails.

    Returns [] when nothing passes the threshold (the caller should treat
    this as a hard refusal — the verifier short-circuits without calling
    Claude). The top score and threshold are logged so operators can tune.
    `caller_context` is appended to the telemetry line (the verifier passes
    `entitlement_id=...` so a single log row is enough to debug a refusal).
    """
    threshold = (
        score_threshold if score_threshold is not None else settings.score_threshold
    )
    today = today or _today_utc()

    vec = embed_query(f"{citation.article} {extra_query}")
    flt = _build_query_filter(citation, profile_canton, today)
    response = _client().query_points(
        collection_name=settings.qdrant_collection,
        query=vec,
        limit=3,
        query_filter=flt,
        with_payload=True,
    )

    chunks: list[RetrievedChunk] = []
    top_score = 0.0
    for r in response.points:
        payload = r.payload or {}
        score = float(r.score)
        if score > top_score:
            top_score = score
        eff_raw = payload.get("effective_date")
        eff_date: date | None = None
        if isinstance(eff_raw, str) and eff_raw:
            try:
                eff_date = date.fromisoformat(eff_raw[:10])
            except ValueError:
                eff_date = None
        chunks.append(
            RetrievedChunk(
                text=str(payload.get("text", "")),
                score=score,
                language=str(payload.get("language", "de")),
                effective_date=eff_date,
            )
        )

    above = [c for c in chunks if c.score >= threshold]
    ctx = f" {caller_context}" if caller_context else ""
    if not above:
        logger.info(
            "retrieval_below_threshold sr=%s art=%s canton=%s "
            "top_score=%.3f threshold=%.3f n_pre=%d%s",
            citation.sr_number,
            citation.article,
            profile_canton,
            top_score,
            threshold,
            len(chunks),
            ctx,
        )
    else:
        logger.debug(
            "retrieval_ok sr=%s art=%s canton=%s top_score=%.3f n=%d%s",
            citation.sr_number,
            citation.article,
            profile_canton,
            above[0].score,
            len(above),
            ctx,
        )
    return above
