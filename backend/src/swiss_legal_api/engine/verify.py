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

# Markers around the chunk JSON block in the user message. Stable so tests
# (and operators reading logs) can extract the structured payload.
_CHUNKS_OPEN = "### RETRIEVED_CHUNKS_JSON ###"
_CHUNKS_CLOSE = "### END_RETRIEVED_CHUNKS ###"

SYSTEM = """You verify whether a specific Swiss legal article supports a specific claimed
entitlement for a specific user context.

Authoritative-source policy:
- Each retrieved chunk has an "is_authoritative" flag and a "language".
- Swiss federal SR (Systematische Rechtssammlung) acts are officially published
  in German, French, and Italian. English Fedlex texts are courtesy translations.
- Prefer chunks where "is_authoritative": true. Treat chunks where
  "is_authoritative": false as a translation aid only.
- If only translation chunks are available, you MAY still verify when the wording
  is unambiguous, but lower your confidence accordingly.

Output rules:
- Output ONLY valid JSON of shape:
  {"supports": bool, "confidence": number 0..1, "reasoning": string,
  "best_quote": string (<= 15 words)}.
- Use the retrieved chunk text as the only source of legal authority.
- Do not hallucinate article text. If no chunk clearly supports the claim,
  set supports=false.
- confidence reflects strength of textual support, not absolute legal certainty."""

_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _is_authoritative_language(sr_number: str, lang: str) -> bool:
    """All Swiss federal SR acts are officially published in DE/FR/IT.

    EN Fedlex texts are courtesy translations, never authoritative. The
    sr_number argument is reserved for future per-SR overrides (e.g. cantonal
    acts published only in a single language).
    """
    del sr_number  # reserved for future per-SR rules
    return lang in {"de", "fr", "it"}


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
    chunks = await asyncio.to_thread(
        retrieve_for_citation,
        cit,
        entitlement.title.en,
        profile.canton,
        None,
        None,
        f"entitlement_id={entitlement.id}",
    )

    # Guardrail: refuse without calling Claude when no chunk passed the
    # similarity threshold + canton/date filters. Saves tokens AND prevents
    # the model from hallucinating against irrelevant context.
    if not chunks:
        logger.info(
            "verify_short_circuit entitlement_id=%s reason=no_chunks_above_threshold "
            "sr=%s art=%s canton=%s",
            entitlement.id,
            cit.sr_number,
            cit.article,
            profile.canton,
        )
        return VerifyResult(
            supports=False,
            confidence=0.0,
            reasoning=(
                "No retrieved chunk above similarity threshold for "
                f"SR {cit.sr_number} Art. {cit.article} in canton "
                f"{profile.canton}; refusing to verify."
            ),
            best_citation=cit,
        )

    # Tag each chunk with is_authoritative. If none are originally
    # authoritative (e.g. only EN translations are in the corpus today),
    # promote them as a graceful fallback so the verifier can still run.
    authoritative_present = any(
        _is_authoritative_language(cit.sr_number, c.language) for c in chunks
    )
    chunk_payload: list[dict[str, Any]] = []
    for c in chunks:
        is_auth = (
            _is_authoritative_language(cit.sr_number, c.language)
            or not authoritative_present
        )
        chunk_payload.append(
            {
                "text": c.text,
                "language": c.language,
                "score": round(c.score, 3),
                "is_authoritative": is_auth,
            }
        )
    # The system prompt promises "authoritative chunks first". Sort here so
    # Claude reads the original-language text before any translation aid,
    # ties broken by retrieval score.
    chunk_payload.sort(
        key=lambda c: (not c["is_authoritative"], -c["score"]),
    )

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

    chunks_block = (
        f"{_CHUNKS_OPEN}\n"
        f"{json.dumps(chunk_payload, indent=2, ensure_ascii=False)}\n"
        f"{_CHUNKS_CLOSE}"
    )

    user_content = f"""Entitlement: {entitlement.title.en}
Claim: This user is entitled to this under SR {cit.sr_number} Art. {cit.article}.
Category: {entitlement.category}
Jurisdiction: {entitlement.jurisdiction}

User profile (structured fields only):
{json.dumps(safe_fields, indent=2)}

Triggering evidence:
{json.dumps(triggered_evidence, indent=2)}

Retrieved legal text (authoritative chunks first):
{chunks_block}

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
    top = chunks[0]
    return VerifyResult(
        supports=bool(parsed.get("supports", False)),
        confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.0)))),
        reasoning=str(parsed.get("reasoning", "")),
        best_citation=cit.model_copy(
            update={
                "quote_under_15_words": quote or cit.quote_under_15_words,
                "effective_date": top.effective_date or cit.effective_date,
                "score": top.score,
            }
        ),
    )
