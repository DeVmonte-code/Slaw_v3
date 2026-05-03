from __future__ import annotations

import asyncio
import logging
import time

import httpx
from anthropic import APIConnectionError, APITimeoutError, AsyncAnthropic, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..catalog import load_catalog
from ..config import settings
from ..engine.agent_runner import (
    RetryableManagedAgentsError as _RetryableManagedAgentsError,
)
from ..engine.retrieval import retrieve_for_citation
from ..schemas import AgentProvenance

logger = logging.getLogger(__name__)

_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    # Same retry parity as engine.verify._call_claude — the managed
    # agents path raises httpx.TransportError on transient failures,
    # which must be retried alongside the legacy Anthropic SDK errors.
    retry=retry_if_exception_type(
        (
            RateLimitError,
            APIConnectionError,
            APITimeoutError,
            httpx.TransportError,
            # Managed-agents semantic retry: server emits
            # ``session.error`` with ``retry_status='retryable'``.
            # Retry with the same backoff. Fatal errors raise
            # ManagedAgentsError instead and are NOT retried.
            _RetryableManagedAgentsError,
        )
    ),
    reraise=True,
)
async def _call_claude(
    message_content: str,
    *,
    site: str = "api.chat",
    user_id: str = "anonymous",
) -> tuple[str, AgentProvenance]:
    """Run one Claude inference for /chat and return (text, provenance).

    Same audit contract as :func:`engine.verify._call_claude` (Task #25).
    /chat answers are not persisted, so the structured ``claude_call`` log
    line is the only audit trail for this call site. When
    ``settings.use_managed_agents`` is True, routes through
    :func:`engine.agent_runner.run_session` (Task #26).
    """
    if settings.use_managed_agents:
        from ..engine.agent_runner import run_session

        return await run_session(
            message_content, site=site, metadata={"user_id": user_id}
        )
    started = time.perf_counter()
    resp = await _anthropic.messages.create(
        model=settings.claude_model,
        max_tokens=800,
        system=(
            "You answer follow-up questions about a specific Swiss legal entitlement. "
            "Cite SR number and article. Keep quotes under 15 words. Remind the user "
            "you are not a Swiss attorney."
        ),
        messages=[{"role": "user", "content": message_content}],
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    text = "".join(b.text for b in resp.content if b.type == "text")
    u = getattr(resp, "usage", None)
    input_tokens = int(getattr(u, "input_tokens", 0) or 0) if u is not None else 0
    output_tokens = int(getattr(u, "output_tokens", 0) or 0) if u is not None else 0
    prov = AgentProvenance(
        call_kind="messages.create",
        agent_backed=False,
        model=settings.claude_model,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    logger.info("%s", prov.to_log_fields(site=site))
    return text, prov


async def answer_follow_up(
    message: str,
    benefit_id: str | None,
    user_id: str = "anonymous",
) -> tuple[str, AgentProvenance]:
    # Managed-agents mode: skip local pre-retrieval entirely. The agent
    # must use swiss-law-retrieval-mcp.fetch_article_by_sr (or
    # qdrant_search) to read the cited article — without that, the
    # call would not register as agent_backed in the audit. The bare
    # benefit_id + user message is the smallest payload that lets the
    # agent decide which MCP tool to invoke.
    if settings.use_managed_agents:
        ent = (
            next((e for e in load_catalog() if e.id == benefit_id), None)
            if benefit_id
            else None
        )
        cit_hint = (
            f"\nCited article hint: SR {ent.source_citations[0].sr_number} "
            f"Art. {ent.source_citations[0].article}"
            if ent is not None
            else ""
        )
        payload = (
            "TASK: answer one user follow-up question about a specific "
            "Swiss legal entitlement.\n\n"
            f"benefit_id: {benefit_id}{cit_hint}\n\n"
            "PROCEDURE:\n"
            "1) If a benefit_id is given, use swiss-law-retrieval-mcp\n"
            "   (fetch_article_by_sr or qdrant_search) to read the\n"
            "   cited article BEFORE answering.\n"
            "2) Cite SR number + article in the answer. Quotes <=15 words.\n"
            "3) End with the standing FADP disclaimer.\n\n"
            f"User question: {message}"
        )
        text, provenance = await _call_claude(
            payload,
            site=f"api.chat:{benefit_id or 'no_benefit'}",
            user_id=user_id,
        )
        # Hard gate (Task #26): if a benefit_id was given, the agent
        # MUST have invoked at least one MCP tool — otherwise it
        # answered from parametric memory and the citation could be
        # hallucinated. We refuse rather than ship an ungrounded
        # answer; the operator sees the warning and can decide whether
        # to roll back the flag or fix the agent's prompt.
        if benefit_id and (provenance.mcp_tool_use_count or 0) == 0:
            from ..engine.agent_runner import ManagedAgentsError

            logger.warning(
                "managed_chat_no_mcp_tools benefit_id=%s session=%s",
                benefit_id,
                provenance.session_id,
            )
            raise ManagedAgentsError(
                "managed_chat_no_mcp_tools "
                f"benefit_id={benefit_id} session_id={provenance.session_id}"
            )
        return text, provenance

    context = ""
    # ``user_id`` is honoured on the legacy messages.create path too —
    # the structured ``claude_call`` log line carries it via the
    # ``site`` field below so per-user audit grep works in both modes.
    _ = user_id
    if benefit_id:
        ent = next((e for e in load_catalog() if e.id == benefit_id), None)
        if ent:
            chunks = await asyncio.to_thread(
                retrieve_for_citation,
                ent.source_citations[0],
                ent.title.en,
                # No profile context in the chat endpoint — fall back to
                # federal-only ("CH"). Cantonal follow-up chat would need
                # the same canton plumbing as /scan.
                "CH",
            )
            context = (
                f"Entitlement: {ent.title.en}\n\n"
                f"Relevant article text:\n"
                + "\n\n".join(c.text for c in chunks)
            )

    payload = f"{context}\n\nUser question: {message}"
    # Provenance is propagated to the caller (and into the /chat
    # response envelope) so auditors can prove a chat answer wasn't
    # produced by a managed agent — Task #25 contract for the
    # non-persisted call site.
    text, provenance = await _call_claude(
        payload, site=f"api.chat:{benefit_id or 'no_benefit'}"
    )
    return text, provenance
