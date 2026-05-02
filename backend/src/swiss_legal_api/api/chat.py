from __future__ import annotations

import asyncio
import logging
import time

from anthropic import APIConnectionError, APITimeoutError, AsyncAnthropic, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..catalog import load_catalog
from ..config import settings
from ..engine.retrieval import retrieve_for_citation
from ..schemas import AgentProvenance

logger = logging.getLogger(__name__)

_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
    reraise=True,
)
async def _call_claude(
    message_content: str, *, site: str = "api.chat"
) -> tuple[str, AgentProvenance]:
    """Run one Claude inference for /chat and return (text, provenance).

    Same audit contract as :func:`engine.verify._call_claude` (Task #25).
    /chat answers are not persisted, so the structured ``claude_call`` log
    line is the only audit trail for this call site.
    """
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
    message: str, benefit_id: str | None
) -> tuple[str, AgentProvenance]:
    context = ""
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
