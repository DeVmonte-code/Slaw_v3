from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from anthropic import APIConnectionError, APITimeoutError, AsyncAnthropic, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings
from ..schemas import Citation, ContextProfile, Entitlement
from .retrieval import retrieve_for_citation

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM = """You verify whether a specific Swiss legal article supports a specific claimed
entitlement for a specific user context.

Rules:
- Output ONLY valid JSON of shape:
  {"supports": bool, "confidence": number 0..1, "reasoning": string,
  "best_quote": string (<= 15 words)}.
- Use the retrieved article text as the authoritative source.
- The retrieved text may be in German (DE) or English (EN); both are authoritative
  Fedlex translations. Reason directly from the text in either language.
- If the article does not support the entitlement for this user context,
  set supports=false and explain why.
- Do not hallucinate article text. If the retrieved text does not clearly
  support the claim, prefer supports=false.
- confidence reflects strength of textual support, not absolute legal certainty."""

_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
    reraise=True,
)
async def _call_claude(user_content: str) -> tuple[str, dict[str, int]]:
    resp = await _anthropic.messages.create(
        model=settings.claude_model,
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    usage: dict[str, int] = {}
    u = getattr(resp, "usage", None)
    if u is not None:
        usage = {
            "input_tokens": int(getattr(u, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
        }
    return text, usage


@dataclass
class VerifyResult:
    supports: bool
    confidence: float
    reasoning: str
    best_citation: Citation


async def verify_entitlement(
    entitlement: Entitlement,
    profile: ContextProfile,
    triggered_evidence: list[dict[str, Any]],
) -> VerifyResult:
    cit = entitlement.source_citations[0]
    chunks = await asyncio.to_thread(retrieve_for_citation, cit, entitlement.title.en)
    retrieved_text = "\n\n".join(
        f"[{i+1}] score={c.score:.3f}: {c.text}" for i, c in enumerate(chunks)
    ) or "NO RESULTS — treat supports as false"

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

    user_content = f"""Entitlement: {entitlement.title.en}
Claim: This user is entitled to this under SR {cit.sr_number} Art. {cit.article}.
Category: {entitlement.category}
Jurisdiction: {entitlement.jurisdiction}

User profile (structured fields only):
{json.dumps(safe_fields, indent=2)}

Triggering evidence:
{json.dumps(triggered_evidence, indent=2)}

Retrieved legal text:
{retrieved_text}

Respond with JSON only."""

    started = time.perf_counter()
    text, usage = await _call_claude(user_content)
    latency_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "claude_verify entitlement_id=%s latency_ms=%d input_tokens=%d output_tokens=%d",
        entitlement.id,
        latency_ms,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
    )

    m = _JSON_RE.search(text)
    raw = m.group(0) if m else text
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "claude_verify_bad_json entitlement_id=%s raw_len=%d",
            entitlement.id,
            len(text),
        )
        return VerifyResult(
            supports=False,
            confidence=0.0,
            reasoning="LLM output was not valid JSON",
            best_citation=cit,
        )

    quote = " ".join(str(parsed.get("best_quote", "")).strip().split()[:14])
    return VerifyResult(
        supports=bool(parsed.get("supports", False)),
        confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.0)))),
        reasoning=str(parsed.get("reasoning", "")),
        best_citation=cit.model_copy(
            update={"quote_under_15_words": quote or cit.quote_under_15_words}
        ),
    )
