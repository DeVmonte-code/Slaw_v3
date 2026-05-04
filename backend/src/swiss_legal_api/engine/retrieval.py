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
    eli_uri: str | None = None
    paragraph: str | None = None


@dataclass
class SupportingChunk:
    """One non-authoritative chunk from the curriculum collection.

    Carries enough metadata for the verifier to surface a transparent "why
    this applies" annotation without ever using it as a primary citation.
    SR + article remain the only binding authority.
    """

    text: str
    score: float
    source_doc: str
    chapter: str | None = None
    section: str | None = None
    page: int | None = None


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def _today_utc() -> date:
    return datetime.now(UTC).date()


def _to_dt_utc(d: date) -> datetime:
    """Promote a date to a UTC datetime at midnight for Qdrant range filters."""
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _build_query_filter(citation: Citation, profile_canton: str, today: date) -> qmodels.Filter:
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
    threshold = score_threshold if score_threshold is not None else settings.score_threshold
    today = today or _today_utc()

    vec = embed_query(f"{citation.article} {extra_query}")
    flt = _build_query_filter(citation, profile_canton, today)
    client = _client()
    # Source-side prune: Qdrant drops sub-threshold chunks before they ever
    # leave the cluster. Defense-in-depth client-side filter below catches
    # any SDK/server skew without a second network round-trip.
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vec,
        limit=3,
        query_filter=flt,
        with_payload=True,
        score_threshold=threshold,
    )

    above: list[RetrievedChunk] = []
    for r in response.points:
        payload = r.payload or {}
        score = float(r.score)
        if score < threshold:
            continue
        eff_raw = payload.get("effective_date")
        eff_date: date | None = None
        if isinstance(eff_raw, str) and eff_raw:
            try:
                eff_date = date.fromisoformat(eff_raw[:10])
            except ValueError:
                eff_date = None
        above.append(
            RetrievedChunk(
                text=str(payload.get("text", "")),
                score=score,
                language=str(payload.get("language", "de")),
                effective_date=eff_date,
                eli_uri=str(payload["eli_uri"]) if payload.get("eli_uri") else None,
                paragraph=str(payload["paragraph"]) if payload.get("paragraph") else None,
            )
        )

    ctx = f" {caller_context}" if caller_context else ""
    if not above:
        # Probe (no threshold) only when above-threshold retrieval was empty,
        # to log the actual top observed score for tuning.
        probe = client.query_points(
            collection_name=settings.qdrant_collection,
            query=vec,
            limit=1,
            query_filter=flt,
            with_payload=False,
        )
        top_score = float(probe.points[0].score) if probe.points else 0.0
        logger.info(
            "retrieval_below_threshold sr=%s art=%s canton=%s top_score=%.3f threshold=%.3f%s",
            citation.sr_number,
            citation.article,
            profile_canton,
            top_score,
            threshold,
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


# Default similarity floor for the curriculum collection. Lower than the
# law-article retriever's threshold because curriculum chunks are wider in
# scope (a doctrine paragraph may only loosely relate to a specific
# entitlement title) — the verifier never relies on these as authority,
# so a permissive floor is fine. Dropping below this only adds noise to
# the verifier prompt without changing the citation contract.
_DEFAULT_CURRICULUM_THRESHOLD = 0.4


def retrieve_supporting_context(
    query: str,
    *,
    topic_tags: list[str] | None = None,
    top_k: int = 3,
    score_threshold: float = _DEFAULT_CURRICULUM_THRESHOLD,
) -> list[SupportingChunk]:
    """Retrieve advisory doctrinal context from the curriculum collection.

    Soft-fails on every error path (collection missing, Qdrant unreachable,
    SDK exception) by logging a warning and returning ``[]``. The verifier
    is built so an empty list is fine — citations stay SR + article and the
    Benefit's ``supporting_doctrine`` is just empty.

    ``topic_tags`` is an optional MatchAny filter against the curriculum
    payload's ``topic_tags`` list field. Use entitlement category as the
    seed tag (e.g. ``["tenancy_right"]``) so contracts-of-obligations
    chunks tagged ``["contracts", "tenancy_right"]`` are preferred.
    """
    if not query.strip():
        return []
    # Fast no-op when Qdrant isn't configured (offline tests, dev workstations
    # without secrets). Avoids triggering the sentence-transformers cold-start
    # via embed_passage and the inevitable Qdrant connection error.
    if not settings.qdrant_url or not settings.curriculum_collection:
        return []
    # The curriculum corpus was indexed with embed_passage at seed time;
    # we use embed_query here because this is the *query* side. E5 (and
    # most modern bi-encoders) use distinct prefixes for "query:" vs
    # "passage:" — mixing them costs retrieval quality. Architect review
    # caught this; keep the asymmetry consistent with engine/retrieval.py
    # line 125 which already uses embed_query for SR/article retrieval.
    try:
        vec = embed_query(query)
    except Exception as exc:
        logger.warning("curriculum_embed_failed exc=%s; returning []", type(exc).__name__)
        return []

    flt: qmodels.Filter | None = None
    if topic_tags:
        flt = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="topic_tags",
                    match=qmodels.MatchAny(any=list(topic_tags)),
                )
            ]
        )

    try:
        response = _client().query_points(
            collection_name=settings.curriculum_collection,
            query=vec,
            limit=top_k,
            query_filter=flt,
            with_payload=True,
            score_threshold=score_threshold,
        )
    except Exception as exc:
        # Most common case: the curriculum collection doesn't exist yet
        # (deployment without seeded PDFs). Don't spam ERROR — this is a
        # designed-for soft-fail path.
        logger.warning(
            "curriculum_retrieval_unavailable collection=%s exc=%s",
            settings.curriculum_collection,
            type(exc).__name__,
        )
        return []

    out: list[SupportingChunk] = []
    for r in response.points:
        payload = r.payload or {}
        out.append(
            SupportingChunk(
                text=str(payload.get("text", "")),
                score=float(r.score),
                source_doc=str(payload.get("source_doc", "")),
                chapter=(str(payload["chapter"]) if payload.get("chapter") else None),
                section=(str(payload["section"]) if payload.get("section") else None),
                page=(int(payload["page"]) if payload.get("page") is not None else None),
            )
        )
    return out
