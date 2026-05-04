from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
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
from ..schemas import (
    AgentProvenance,
    Benefit,
    BenefitReport,
    Citation,
    ContextProfile,
    Entitlement,
    EvidenceItem,
)
from .trigger import evaluate_trigger
from .verify import VerifyResult, verify_entitlement

# Reasoning string the managed driver attaches when an agent verdict is
# rejected because its claimed citation does not resolve to a real
# corpus article (or because no MCP tool was invoked at all). Stable so
# tests and dashboards can pin on it.
_REQUIRES_EVIDENCE_REVIEW = (
    "requires_evidence_review: managed agent verdict could not be "
    "grounded in a corpus citation"
)

_AGENT_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

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


def _build_agent_brief(
    profile: ContextProfile,
    triggered: list[tuple[Entitlement, list[dict[str, Any]]]],
) -> str:
    """Render the single-session task brief listing every triggered entitlement.

    The agent receives JUST IDs, titles, and seed-citation hints (SR +
    article) per entitlement — never the chunks themselves. It must
    invoke the MCP tools to fetch the authoritative text and decide
    each verdict. Output schema is fixed so the parser can rebuild
    one ``VerifyResult`` per entitlement deterministically.
    """
    safe_fields = {
        "canton": profile.canton,
        "employment_status": profile.employment_status,
        "housing_status": profile.housing_status,
        "household_size": profile.household_size,
        "children_count": profile.children_count,
        "marital_status": profile.marital_status,
        "income_band_chf": profile.income_band_chf,
        "business_activity": profile.business_activity,
    }
    items: list[dict[str, Any]] = []
    for e, evidence in triggered:
        items.append(
            {
                "entitlement_id": e.id,
                "title": e.title.en,
                "category": e.category,
                "jurisdiction": e.jurisdiction,
                "seed_citations": [
                    {
                        "sr_number": c.sr_number,
                        "article": c.article,
                        "paragraph": c.paragraph,
                        "language": c.language,
                    }
                    for c in e.source_citations
                ],
                "triggered_evidence": evidence,
            }
        )
    return (
        "TASK: verify a batch of triggered Swiss legal entitlements for one user.\n\n"
        "user_profile (structured fields, JSON):\n"
        f"{json.dumps(safe_fields, indent=2)}\n\n"
        "triggered_entitlements (JSON array):\n"
        f"{json.dumps(items, indent=2)}\n\n"
        "PROCEDURE (mandatory — follow EXACTLY):\n"
        "1) For EACH entitlement_id call swiss-law-retrieval-mcp.qdrant_search\n"
        "   using the seed_citation sr_number and article. This returns chunks\n"
        "   from the local corpus. Each chunk may include an 'eli_uri' field —\n"
        "   this is the official Fedlex linked-data URI for that law article.\n\n"
        "2) For every unique eli_uri returned in step 1, call\n"
        "   swiss-law-retrieval-mcp.fetch_fedlex_article(\n"
        "     eli_uri=<uri>, article=<article from the matching seed_citation>\n"
        "   ).\n"
        "   This fetches the FULL live article text from the official Swiss\n"
        "   Fedlex filestore (fedlex.data.admin.ch). The returned 'article_text'\n"
        "   and 'paragraphs' fields contain the authoritative wording as\n"
        "   published today — use them as primary evidence to determine what\n"
        "   benefits the user profile qualifies for.\n"
        "   If 'article_text' differs materially from the Qdrant chunk text,\n"
        "   prefer the Fedlex text and note the discrepancy in 'reasoning'.\n"
        "   If 'article_text' is empty (e.g. error≠null), fall back to the\n"
        "   Qdrant chunk text and state this in 'reasoning'.\n\n"
        "3) For EACH entitlement_id call\n"
        "   swiss-contract-tools-mcp.verify_entitlement passing:\n"
        "     - entitlement_id: the string ID\n"
        "     - profile: the user_profile dict above\n"
        "   Ground your reasoning in the Fedlex text fetched in step 2.\n"
        "   The tool returns: {entitlement_id, supports, confidence,\n"
        "   reasoning, best_citation{sr_number, article, paragraph,\n"
        "   language, quote_under_15_words}}.\n\n"
        "4) After ALL tool calls are complete, your ENTIRE TEXT RESPONSE\n"
        "   MUST be ONLY the following JSON object — no preamble, no\n"
        "   explanation, no markdown fences. Start with '{' and end\n"
        "   with '}'. Any other text will cause every benefit to be\n"
        "   suppressed as unverified.\n\n"
        "OUTPUT JSON (copy the tool results directly into this shape):\n"
        "{\n"
        '  "verifications": [\n'
        "    {\n"
        '      "entitlement_id": "<same id you passed to the tool>",\n'
        '      "supports": <bool from tool result>,\n'
        '      "confidence": <number 0..1 from tool result>,\n'
        '      "reasoning": "<reasoning from tool result, grounded in Fedlex text>",\n'
        '      "best_citation": {\n'
        '        "sr_number": "<from tool result>",\n'
        '        "article": "<from tool result>",\n'
        '        "paragraph": <str or null from tool result>,\n'
        '        "language": "<de|fr|it|en from tool result>",\n'
        '        "quote_under_15_words": "<from tool result>"\n'
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "CRITICAL RULES:\n"
        "- Always call fetch_fedlex_article for every eli_uri you find.\n"
        "  If qdrant_search returns no eli_uri, fall back to the Qdrant\n"
        "  chunk text alone and note it in reasoning.\n"
        "- Include EVERY entitlement_id from the input list, even when\n"
        "  supports=false.\n"
        "- Do NOT add any text outside the JSON object.\n"
        "- Do NOT wrap the JSON in markdown code fences.\n"
        "- Copy field values directly from the tool results — do not\n"
        "  rephrase, summarise, or omit any field.\n"
    )


def _parse_agent_verifications(text: str) -> dict[str, dict[str, Any]]:
    """Extract the ``{entitlement_id: entry}`` map from the agent's reply.

    Returns an empty dict when the reply is not parseable JSON or when
    it lacks the expected ``verifications`` array. The caller then
    suppresses every triggered entitlement with the standard
    ``requires_evidence_review`` reason — i.e. a malformed reply degrades
    to "no benefits" rather than silently fabricating verdicts.
    """
    m = _AGENT_JSON_RE.search(text or "")
    raw = m.group(0) if m else (text or "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    entries = parsed.get("verifications") if isinstance(parsed, dict) else None
    if not isinstance(entries, list):
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("entitlement_id")
        if isinstance(eid, str) and eid:
            by_id[eid] = entry
    return by_id


def _verify_result_unsupported(
    cit: Citation,
    reasoning: str,
    provenance: AgentProvenance | None,
) -> VerifyResult:
    kwargs: dict[str, Any] = {
        "supports": False,
        "confidence": 0.0,
        "reasoning": reasoning,
        "best_citation": cit,
    }
    if provenance is not None:
        kwargs["agent_provenance"] = provenance
    return VerifyResult(**kwargs)


async def _resolve_agent_citation(
    entry: dict[str, Any],
    fallback: Citation,
    profile_canton: str,
    entitlement_id: str,
) -> tuple[Citation | None, list[Any]]:
    """Build a Pydantic ``Citation`` from the agent's reply and probe it.

    Returns ``(citation, chunks)``:
      - ``citation`` is None when the agent's payload is structurally
        invalid (missing fields, validation error). The caller suppresses.
      - ``chunks`` is the retrieval probe result against that citation.
        An empty list means "citation does not resolve to corpus" and
        the caller suppresses with ``requires_evidence_review``.

    We import ``retrieve_for_citation`` lazily and run it in a worker
    thread so this function is safely callable from the asyncio event
    loop without blocking on Qdrant I/O.
    """
    from .retrieval import retrieve_for_citation

    # Accept both "citation" (legacy prompt schema) and "best_citation"
    # (matches verify_entitlement tool output directly).
    raw_cit = entry.get("citation") or entry.get("best_citation")
    if not isinstance(raw_cit, dict):
        return None, []
    # Accept quote from best_quote (legacy) or quote_under_15_words (tool output).
    raw_quote = entry.get("best_quote") or raw_cit.get("quote_under_15_words", "")
    quote = " ".join(str(raw_quote).strip().split()[:14]) or "n/a"
    try:
        cit = Citation(
            sr_number=str(raw_cit.get("sr_number", "")),
            article=str(raw_cit.get("article", "")),
            paragraph=raw_cit.get("paragraph"),
            canton=str(raw_cit.get("canton") or fallback.canton),
            language=raw_cit.get("language") or fallback.language,
            quote_under_15_words=quote,
        )
    except Exception as exc:
        logger.info(
            "managed_scan_bad_citation entitlement_id=%s exc=%s",
            entitlement_id,
            type(exc).__name__,
        )
        return None, []
    try:
        chunks = await asyncio.to_thread(
            retrieve_for_citation,
            cit,
            "",
            profile_canton,
            None,
            None,
            f"managed-scan-resolve entitlement_id={entitlement_id}",
        )
    except Exception as exc:
        logger.warning(
            "managed_scan_resolve_probe_failed entitlement_id=%s exc=%s",
            entitlement_id,
            type(exc).__name__,
        )
        chunks = []
    return cit, chunks


_TOOL_LABELS: dict[str, str] = {
    "qdrant_search": "Searching Swiss federal law",
    "fetch_article_by_sr": "Fetching cited article",
    "verify_entitlement": "Cross-checking entitlement against the corpus",
    "benefit_scan": "Running batched benefit scan",
    "get_user_profile": "Reading your profile",
}


def _humanize_tool_call(tool: str, server: str | None) -> str:
    """Map an MCP tool name (and optional server hint) to a UI label.

    Falls back to a generic ``"Calling <tool>"`` so a brand-new tool
    still renders something useful in the live feed without forcing a
    code change here. Server hint is appended to disambiguate cases
    where two MCPs expose the same tool name (e.g. retrieval helpers).
    """
    label = _TOOL_LABELS.get(tool)
    if label:
        return label
    if tool:
        return f"Calling {tool}"
    return "Working with the agent"


def _make_agent_event_cb(
    progress_cb: ProgressCallback | None,
) -> Any:
    """Build the per-event forwarder the managed-agents runner invokes.

    Translates ``agent.mcp_tool_use`` / ``agent.tool_use`` SSE events
    into ``tool_call`` progress events so /scan/stream can show the
    real, agent-driven activity instead of the timer-driven phase
    ticker. ``agent.message`` events are intentionally NOT forwarded
    — the verbatim agent output is JSON the parser owns; surfacing it
    raw to the UI would be noisy and could leak intermediate planning
    tokens.
    """
    if progress_cb is None:
        return None

    async def _forward(event: dict[str, Any]) -> None:
        et = event.get("type")
        if et not in ("agent.mcp_tool_use", "agent.tool_use"):
            return
        tool = str(event.get("name") or event.get("tool_name") or "")
        srv_raw = event.get("server_name") or event.get("mcp_server_name")
        server = srv_raw if isinstance(srv_raw, str) and srv_raw else None
        await _emit(
            progress_cb,
            {
                "type": "tool_call",
                "tool": tool,
                "server": server,
                "label": _humanize_tool_call(tool, server),
            },
        )

    return _forward


async def _verify_via_managed_session(
    profile: ContextProfile,
    triggered: list[tuple[Entitlement, list[dict[str, Any]]]],
    user_id: str,
    progress_cb: ProgressCallback | None = None,
) -> dict[str, VerifyResult]:
    """Drive verification of every triggered entitlement in ONE session.

    Replaces the per-entitlement fan-out on the managed-agents path.
    Returns ``{entitlement_id: VerifyResult}`` for every entitlement in
    ``triggered``. Failure modes fold into per-entitlement
    ``supports=False`` results carrying the ``requires_evidence_review``
    reason so ``run_benefit_scan`` can keep its single suppress branch.

    A managed session that streams zero MCP tool uses is treated as
    ungrounded — the same hard gate the per-entitlement path applies.
    A fatal :class:`ManagedAgentsError` is re-raised so the operator
    sees a 5xx, mirroring ``_verify_one``.
    """
    # Lazy import so test environments that never set use_managed_agents
    # don't pay the SSE-streaming machinery's cold-start cost.
    from .agent_runner import ManagedAgentsError, run_session

    brief = _build_agent_brief(profile, triggered)
    text, provenance = await run_session(
        brief,
        site="engine.scan.batch",
        metadata={"user_id": user_id},
        event_cb=_make_agent_event_cb(progress_cb),
    )
    logger.info(
        "managed_scan_session entitlements=%d session=%s "
        "agent_backed=%s tools=%d mcp_tools=%d latency_ms=%d",
        len(triggered),
        provenance.session_id,
        str(provenance.agent_backed).lower(),
        provenance.tool_use_count or 0,
        provenance.mcp_tool_use_count or 0,
        provenance.latency_ms,
    )

    results: dict[str, VerifyResult] = {}
    # Hard gate: a session that never invoked an MCP tool cannot have
    # produced grounded verdicts. Suppress every entitlement.
    if (provenance.mcp_tool_use_count or 0) == 0:
        logger.warning(
            "managed_scan_no_mcp_tools session=%s entitlements=%d",
            provenance.session_id,
            len(triggered),
        )
        for e, _ev in triggered:
            results[e.id] = _verify_result_unsupported(
                e.source_citations[0],
                _REQUIRES_EVIDENCE_REVIEW,
                provenance,
            )
        return results

    by_id = _parse_agent_verifications(text)
    if not by_id:
        logger.warning(
            "managed_scan_bad_reply session=%s raw_len=%d",
            provenance.session_id,
            len(text or ""),
        )

    for e, _ev in triggered:
        entry = by_id.get(e.id)
        seed = e.source_citations[0]
        if entry is None:
            results[e.id] = _verify_result_unsupported(
                seed, _REQUIRES_EVIDENCE_REVIEW, provenance
            )
            continue

        try:
            confidence = max(0.0, min(1.0, float(entry.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        supports = bool(entry.get("supports", False))
        reasoning = str(entry.get("reasoning", "")).strip()

        if not supports:
            # The agent itself decided the article does not support the
            # claim — keep its reasoning, fall back to seed citation
            # since we don't need to prove a positive grounding.
            results[e.id] = VerifyResult(
                supports=False,
                confidence=confidence,
                reasoning=reasoning or "Agent verdict: not supported.",
                best_citation=seed,
                agent_provenance=provenance,
            )
            continue

        cit, chunks = await _resolve_agent_citation(
            entry, seed, profile.canton, e.id
        )
        if cit is None or not chunks:
            logger.info(
                "managed_scan_unresolved_citation entitlement_id=%s "
                "session=%s",
                e.id,
                provenance.session_id,
            )
            results[e.id] = _verify_result_unsupported(
                seed, _REQUIRES_EVIDENCE_REVIEW, provenance
            )
            continue

        top = chunks[0]
        results[e.id] = VerifyResult(
            supports=True,
            confidence=confidence,
            reasoning=reasoning or "Agent verdict: supported.",
            best_citation=cit.model_copy(
                update={
                    "effective_date": top.effective_date or cit.effective_date,
                    "score": top.score,
                }
            ),
            agent_provenance=provenance,
        )

    # Re-raise of ManagedAgentsError happens naturally because run_session
    # raises it before this function can return — name-checked here as a
    # contract reminder so a future refactor doesn't drop the import.
    _ = ManagedAgentsError
    return results


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

    # Verification dispatch:
    #   * managed-agents driver path — one session for the whole batch,
    #     guarded by ``settings.use_managed_agents`` and disabled when
    #     ``force_local=True`` (the MCP ``benefit_scan`` wrapper passes
    #     that to avoid a managed-session-inside-a-managed-session
    #     recursion).
    #   * local fan-out — one verifier call per entitlement, the
    #     pre-Task-#36 behaviour. Still what the MCP wrapper, the
    #     ``use_managed_agents=False`` dev path, and the test suite
    #     exercise.
    use_agent_driver = settings.use_managed_agents and not force_local

    verified_count = 0
    suppressed_running = 0
    results: list[tuple[Entitlement, list[dict[str, Any]], VerifyResult | None]] = (
        [None] * total  # type: ignore[list-item]
    )

    if use_agent_driver and total:
        for idx, (e, ev) in enumerate(triggered):
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
                    "index": idx,
                    "total": total,
                },
            )
        # ManagedAgentsError fatal failures bubble up so /scan returns
        # 5xx — same posture as the per-entitlement fan-out's re-raise.
        verdicts_by_id = await _verify_via_managed_session(
            profile, triggered, user_id, progress_cb=progress_cb
        )
        for idx, (e, ev) in enumerate(triggered):
            v = verdicts_by_id.get(e.id)
            results[idx] = (e, ev, v)
            title = str(getattr(e.title, profile.language, None) or e.title.en)
            if v is None or not v.supports or v.confidence < e.confidence_floor:
                suppressed_running += 1
                supported_event = False
            else:
                verified_count += 1
                supported_event = True
            await _emit(
                progress_cb,
                {
                    "type": "verified",
                    "entitlement_id": e.id,
                    "title": title,
                    "supported": supported_event,
                    "confidence": float(v.confidence) if v else 0.0,
                    "verified_count": verified_count,
                    "suppressed_count": suppressed_running,
                    "total": total,
                },
            )

    else:
        sem = asyncio.Semaphore(settings.scan_concurrency)

        # Wrap each verification so we can emit a "verified" event the
        # moment the future resolves — gather() preserves input order, but
        # for honest streaming we want the real completion order, so we
        # use as_completed and rebuild the list afterwards.

        async def _wrapped(
            idx: int, e: Entitlement, ev: list[dict[str, Any]]
        ) -> tuple[
            int, tuple[Entitlement, list[dict[str, Any]], VerifyResult | None]
        ]:
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

        coros = [
            _wrapped(i, e, ev) for i, (e, ev) in enumerate(triggered)
        ]
        for coro in asyncio.as_completed(coros):
            idx, out = await coro
            results[idx] = out
            e, _ev, v = out
            event_title = str(getattr(e.title, profile.language, None) or e.title.en)
            if v is None or not v.supports or v.confidence < e.confidence_floor:
                suppressed_running += 1
                await _emit(
                    progress_cb,
                    {
                        "type": "verified",
                        "entitlement_id": e.id,
                        "title": event_title,
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
                        "title": event_title,
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
        out_title: str = str(getattr(e.title, profile.language, None) or e.title.en)
        benefits.append(
            Benefit(
                entitlement_id=e.id,
                title=out_title,
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
