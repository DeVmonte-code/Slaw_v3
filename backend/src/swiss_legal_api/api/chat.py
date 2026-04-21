from __future__ import annotations

import asyncio

from anthropic import AsyncAnthropic

from ..catalog import load_catalog
from ..config import settings
from ..engine.retrieval import retrieve_for_citation

_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def answer_follow_up(message: str, benefit_id: str | None) -> str:
    context = ""
    if benefit_id:
        ent = next((e for e in load_catalog() if e.id == benefit_id), None)
        if ent:
            chunks = await asyncio.to_thread(
                retrieve_for_citation, ent.source_citations[0], ent.title.en
            )
            context = (
                f"Entitlement: {ent.title.en}\n\n"
                f"Relevant article text:\n"
                + "\n\n".join(c.text for c in chunks)
            )

    resp = await _anthropic.messages.create(
        model=settings.claude_model,
        max_tokens=800,
        system=(
            "You answer follow-up questions about a specific Swiss legal entitlement. "
            "Cite SR number and article. Keep quotes under 15 words. Remind the user "
            "you are not a Swiss attorney."
        ),
        messages=[{"role": "user", "content": f"{context}\n\nUser question: {message}"}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")
