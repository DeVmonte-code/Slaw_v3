from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import settings
from ..schemas import Benefit, BenefitReport, ContextProfile, Entitlement, EvidenceItem
from .trigger import evaluate_trigger
from .verify import VerifyResult, verify_entitlement

logger = logging.getLogger(__name__)


# Mirrored from swiss_legal_api.seeding.seed_qdrant._PLACEHOLDER_SENTINEL.
# Kept local so the request path doesn't import qdrant_client transitively.
# If this string ever changes, update both copies (the seeder hard-fails if a
# sentinel sneaks past, so a drift would surface during the next reindex).
_PLACEHOLDER_SENTINEL = "__PENDING_FEDLEX_VERBATIM__"

_LAW_ARTICLES_PATH = (
    Path(__file__).resolve().parents[3] / "seed" / "law_articles.json"
)


@lru_cache(maxsize=1)
def _pending_corpus_articles() -> frozenset[tuple[str, str]]:
    """Return ``(sr_number, article)`` keys whose seed text is still the
    ``__PENDING_FEDLEX_VERBATIM__`` sentinel.

    The seeder filters these rows out before they reach Qdrant, so any
    entitlement that only cites placeholder articles cannot be verified —
    retrieval comes back empty and Claude is called against a hard refusal
    payload (or, worse, against the literal sentinel string if a future
    seeder bug ever embeds one). Loading the manual seed once and using it
    as a skip-list lets ``run_benefit_scan`` short-circuit before paying
    for the embedding query, the Qdrant round-trip, and the Claude call.

    Returns an empty frozenset if the seed file is missing or no row
    matches — the guard then becomes a no-op, which is exactly what we
    want once the Fedlex backfill follow-up lands.
    """
    try:
        rows = json.loads(_LAW_ARTICLES_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return frozenset()
    pending: set[tuple[str, str]] = set()
    for r in rows:
        text = r.get("text") if isinstance(r, dict) else None
        # Substring match (not strict equality) intentionally mirrors the
        # seeder's `_is_placeholder`, so a future seed template that wraps
        # the sentinel in TODO prose still gets caught by both layers.
        if isinstance(text, str) and _PLACEHOLDER_SENTINEL in text:
            sr = str(r.get("sr_number", "") or "")
            art = str(r.get("article", "") or "")
            if sr and art:
                pending.add((sr, art))
    return frozenset(pending)


def _all_citations_pending(
    entitlement: Entitlement, pending: frozenset[tuple[str, str]]
) -> bool:
    """True iff every source citation of ``entitlement`` is in ``pending``.

    We deliberately require *all* citations to be placeholders before
    skipping: if even one citation has real Fedlex text, the verifier can
    still produce a meaningful (if narrower) verdict for the user.
    """
    cits = entitlement.source_citations
    if not cits:
        return False
    return all((c.sr_number, c.article) in pending for c in cits)


async def _verify_one(
    e: Entitlement,
    profile: ContextProfile,
    evidence: list[dict[str, Any]],
    sem: asyncio.Semaphore,
    user_id: str = "anonymous",
) -> tuple[Entitlement, list[dict[str, Any]], VerifyResult | None]:
    async with sem:
        try:
            v = await verify_entitlement(e, profile, evidence, user_id=user_id)
            return e, evidence, v
        except Exception as exc:
            # Managed-agents fatal errors (terminated session, fatal
            # session.error) MUST surface to the operator — silently
            # turning them into "fewer benefits" hides outages and
            # defeats the audit trail. Re-raise so /scan returns 5xx.
            from .agent_runner import ManagedAgentsError

            if isinstance(exc, ManagedAgentsError):
                logger.error(
                    "verify_entitlement managed-fatal entitlement_id=%s exc=%s",
                    e.id,
                    exc,
                )
                raise
            logger.exception(
                "verify_entitlement failed for entitlement_id=%s exc_type=%s",
                e.id,
                type(exc).__name__,
            )
            return e, evidence, None


async def run_benefit_scan(
    profile: ContextProfile,
    catalog: list[Entitlement],
    user_id: str = "anonymous",
) -> BenefitReport:
    started = time.perf_counter()

    pending_articles = _pending_corpus_articles()
    triggered: list[tuple[Entitlement, list[dict[str, Any]]]] = []
    pending_corpus_backfill = 0
    for e in catalog:
        r = evaluate_trigger(e.trigger, profile)
        if not r.matched:
            continue
        if _all_citations_pending(e, pending_articles):
            # Skip Claude entirely: every cited article is still a
            # placeholder, so retrieval would either return nothing or
            # the literal sentinel chunk. Either way the verdict is a
            # foregone suppression — paying for the call is pure waste.
            pending_corpus_backfill += 1
            logger.info(
                "scan_skip_pending_corpus_backfill entitlement_id=%s "
                "citations=%s",
                e.id,
                ",".join(
                    f"SR{c.sr_number}/Art{c.article}" for c in e.source_citations
                ),
            )
            continue
        triggered.append((e, r.evidence))

    sem = asyncio.Semaphore(settings.scan_concurrency)
    results = await asyncio.gather(
        *[_verify_one(e, profile, ev, sem, user_id) for e, ev in triggered]
    )

    benefits: list[Benefit] = []
    suppressed = 0
    for e, evidence, v in results:
        if v is None or not v.supports or v.confidence < e.confidence_floor:
            suppressed += 1
            continue
        title: str = str(getattr(e.title, profile.language, None) or e.title.en)
        benefits.append(
            Benefit(
                entitlement_id=e.id,
                title=title,
                category=e.category,
                estimated_value_chf=e.estimated_value_chf,
                confidence=v.confidence,
                citations=[v.best_citation, *e.source_citations[1:]],
                evidence=[EvidenceItem(**ev) for ev in evidence],
                required_action=e.required_action,
                action_template_id=e.action_template_id,
                time_limit_days=e.time_limit_days,
                llm_reasoning=v.reasoning,
                supporting_doctrine=v.supporting_doctrine,
                agent_provenance=v.agent_provenance,
            )
        )

    benefits.sort(
        key=lambda b: b.confidence * math.log1p(b.estimated_value_chf.max),
        reverse=True,
    )

    profile_hash = hashlib.sha256(
        json.dumps(profile.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()[:16]

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "scan_complete profile_hash=%s triggered=%d verified=%d "
        "suppressed=%d pending_corpus_backfill=%d duration_ms=%d",
        profile_hash,
        len(triggered),
        len(benefits),
        suppressed,
        pending_corpus_backfill,
        duration_ms,
    )

    return BenefitReport(
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        profile_hash=profile_hash,
        benefits=benefits,
        suppressed_count=suppressed,
        pending_corpus_backfill=pending_corpus_backfill,
    )
