from __future__ import annotations

import asyncio
import logging

from anthropic import APIConnectionError, APITimeoutError, AsyncAnthropic, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..catalog import load_catalog
from ..config import settings
from ..engine.retrieval import retrieve_for_citation

logger = logging.getLogger(__name__)

_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
    reraise=True,
)
async def _call_claude(message_content: str) -> str:
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
    return "".join(b.text for b in resp.content if b.type == "text")


async def answer_follow_up(message: str, benefit_id: str | None) -> str:
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
    return await _call_claude(payload)
