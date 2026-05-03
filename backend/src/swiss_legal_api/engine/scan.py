from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

# Type alias: an async progress callback invoked by ``run_benefit_scan`` at
# meaningful state transitions (phase boundaries, per-entitlement verify
# start/finish, completion). The /scan/stream SSE endpoint hands in a
# callback that pushes events onto an asyncio.Queue; plain /scan callers
# pass ``None`` and the function behaves exactly as before.
ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

from ..config import settings
from ..schemas import Benefit, BenefitReport, ContextProfile, Entitlement, EvidenceItem
from .trigger import evaluate_trigger
from .verify import VerifyResult, verify_entitlement

logger = logging.getLogger(__name__)


async def _emit(cb: ProgressCallback | None, event: dict[str, Any]) -> None:
    """Best-effort progress emit. A failing callback (slow consumer,
    closed queue, disconnected SSE client) MUST NOT abort the scan —
    we log and swallow so the report still completes for the caller
    that is still listening, or for the sweep job that doesn't care."""
    if cb is None:
        return
    try:
        await cb(event)
    except Exception as exc:
        logger.debug("scan_progress_emit_failed err=%s", type(exc).__name__)


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
    force_local: bool = False,
    progress_cb: ProgressCallback | None = None,
    index: int = 0,
    total: int = 0,
) -> tuple[Entitlement, list[dict[str, Any]], VerifyResult | None]:
    async with sem:
        title_for_event = str(
            getattr(e.title, profile.language, None) or e.title.en
        )
        await _emit(
            progress_cb,
            {
                "type": "verifying",
                "entitlement_id": e.id,
                "title": title_for_event,
                "category": e.category,
                "index": index,
                "total": total,
            },
        )
        try:
            if force_local:
                # Used by the MCP ``benefit_scan`` tool wrapper to avoid
                # fan-out: when an agent calls ``benefit_scan`` we MUST
                # NOT spawn one managed session per entitlement (would
                # recurse inside a managed session). The local verifier
                # path is identical code, just without the managed-
                # agents indirection.
                from .verify import _verify_local

                v = await _verify_local(e, profile, evidence)
            else:
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
    force_local: bool = False,
    progress_cb: ProgressCallback | None = None,
) -> BenefitReport:
    started = time.perf_counter()

    await _emit(
        progress_cb,
        {
            "type": "phase",
            "name": "trigger",
            "message": "Reading your profile",
        },
    )

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

    total = len(triggered)
    await _emit(
        progress_cb,
        {
            "type": "triggered",
            "count": total,
            "pending_corpus_backfill": pending_corpus_backfill,
        },
    )
    await _emit(
        progress_cb,
        {
            "type": "phase",
            "name": "verify",
            "message": (
                f"Verifying {total} potential benefit(s) against Swiss law"
                if total
                else "No matching entitlements triggered"
            ),
        },
    )

    sem = asyncio.Semaphore(settings.scan_concurrency)

    # Wrap each verification so we can emit a "verified" event the
    # moment the future resolves — gather() preserves input order, but
    # for honest streaming we want the real completion order, so we
    # use as_completed and rebuild the list afterwards.
    verified_count = 0
    suppressed_running = 0

    async def _wrapped(
        idx: int, e: Entitlement, ev: list[dict[str, Any]]
    ) -> tuple[int, tuple[Entitlement, list[dict[str, Any]], VerifyResult | None]]:
        out = await _verify_one(
            e,
            profile,
            ev,
            sem,
            user_id,
            force_local,
            progress_cb=progress_cb,
            index=idx,
            total=total,
        )
        return idx, out

    results: list[tuple[Entitlement, list[dict[str, Any]], VerifyResult | None]] = (
        [None] * total  # type: ignore[list-item]
    )
    coros = [
        _wrapped(i, e, ev) for i, (e, ev) in enumerate(triggered)
    ]
    for coro in asyncio.as_completed(coros):
        idx, out = await coro
        results[idx] = out
        e, _ev, v = out
        title = str(getattr(e.title, profile.language, None) or e.title.en)
        if v is None or not v.supports or v.confidence < e.confidence_floor:
            suppressed_running += 1
            await _emit(
                progress_cb,
                {
                    "type": "verified",
                    "entitlement_id": e.id,
                    "title": title,
                    "supported": False,
                    "confidence": float(v.confidence) if v else 0.0,
                    "verified_count": verified_count,
                    "suppressed_count": suppressed_running,
                    "total": total,
                },
            )
        else:
            verified_count += 1
            await _emit(
                progress_cb,
                {
                    "type": "verified",
                    "entitlement_id": e.id,
                    "title": title,
                    "supported": True,
                    "confidence": float(v.confidence),
                    "verified_count": verified_count,
                    "suppressed_count": suppressed_running,
                    "total": total,
                },
            )

    await _emit(
        progress_cb,
        {
            "type": "phase",
            "name": "report",
            "message": "Drafting your report",
        },
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
