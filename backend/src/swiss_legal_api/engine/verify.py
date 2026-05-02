from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from anthropic import APIConnectionError, APITimeoutError, AsyncAnthropic, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings
from ..schemas import (
    AgentProvenance,
    Citation,
    ContextProfile,
    Entitlement,
    SupportingDoctrine,
)
from .retrieval import retrieve_for_citation, retrieve_supporting_context

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# Markers around the chunk JSON block in the user message. Stable so tests
# (and operators reading logs) can extract the structured payload.
_CHUNKS_OPEN = "### RETRIEVED_CHUNKS_JSON ###"
_CHUNKS_CLOSE = "### END_RETRIEVED_CHUNKS ###"

SYSTEM = """You verify whether a specific Swiss legal article supports a specific claimed
entitlement for a specific user context.

Authoritative-source policy:
- Swiss federal SR (Systematische Rechtssammlung) acts are officially published
  in German, French, and Italian. English Fedlex texts are courtesy translations
  and are NEVER authoritative.
- Each retrieved chunk has a strict "is_authoritative" flag (true only for
  DE/FR/IT) and a "language".
- Prefer chunks where "is_authoritative": true. Treat chunks where
  "is_authoritative": false as a translation aid only.
- The user message also includes a top-level "translation_only" flag. When
  translation_only=true, NO authoritative chunk was retrieved. You MAY still
  verify when the translated wording is unambiguous and clearly on-point, but
  lower confidence accordingly (cap at 0.75) and note the lack of original-
  language source in your reasoning.

Supporting-doctrine policy:
- The user message MAY include a "supporting_doctrine" array of paragraphs
  drawn from Swiss legal commentary (e.g. CO 1-183 doctrinal text). These
  are advisory background ONLY — they help you understand context but are
  NEVER a substitute for the SR + article authority and MUST NOT be used as
  the basis of your verification. If "chunks" is empty or unsupportive, do
  NOT verify on doctrine alone — respond supports=false.
- Do NOT cite the doctrine in "best_quote"; "best_quote" must come from the
  retrieved SR/article chunks.

Output rules:
- Output ONLY valid JSON of shape:
  {"supports": bool, "confidence": number 0..1, "reasoning": string,
  "best_quote": string (<= 15 words)}.
- Use the retrieved chunk text as the only source of legal authority.
- Do not hallucinate article text. If no chunk clearly supports the claim,
  set supports=false.
- confidence reflects strength of textual support, not absolute legal certainty."""

_anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)


# Server-side enforcement of the prompt's translation-only confidence cap.
# Mirrors the value stated in the SYSTEM prompt above so the policy is
# guaranteed even if Claude ignores the instruction.
_TRANSLATION_ONLY_CONFIDENCE_CAP = 0.75

_FEDERAL_AUTH_LANGS = frozenset({"de", "fr", "it"})

# Per-SR original-language provenance. Federal SR acts (every entry currently
# in seed/law_articles.json) are officially published in DE/FR/IT, so the map
# defaults to that set via _AUTH_LANGS_BY_SR.get(sr, _FEDERAL_AUTH_LANGS).
# Cantonal acts ingested by Task #20 will register their own original-language
# set here (e.g. Ticino → frozenset({"it"})), and EN remains a translation aid
# in every case.
_AUTH_LANGS_BY_SR: dict[str, frozenset[str]] = {}


def _is_authoritative_language(sr_number: str, lang: str) -> bool:
    """Return True iff `lang` is one of the SR's official publication languages.

    Defaults to the federal {de, fr, it} set when the SR has no explicit
    provenance override. EN is never authoritative (Fedlex EN is a courtesy
    translation), regardless of SR.
    """
    return lang in _AUTH_LANGS_BY_SR.get(sr_number, _FEDERAL_AUTH_LANGS)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
    reraise=True,
)
async def _call_claude(
    user_content: str, *, site: str = "engine.verify"
) -> tuple[str, AgentProvenance]:
    """Run one Claude inference and return (text, provenance).

    Provenance is the audit contract for Task #25: every Claude call in
    the codebase emits a structured ``claude_call`` log line and returns
    an :class:`AgentProvenance`. Today's path is always
    ``call_kind="messages.create"`` and ``agent_backed=False`` — Task #26
    will flip the call sites to ``sessions.events`` and the same
    contract will start surfacing tool-use evidence.
    """
    started = time.perf_counter()
    resp = await _anthropic.messages.create(
        model=settings.claude_model,
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_content}],
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
    # One stable structured line per Claude call carrying the FULL
    # provenance contract (nullable managed-agent fields included as
    # empty values on the messages.create baseline). The audit endpoint
    # and CLI parse persisted Benefit.agent_provenance, but ``/chat``
    # and any future non-persisted call site still leave an audit trail
    # here that auditors can grep with one ``claude_call`` selector.
    logger.info("%s", prov.to_log_fields(site=site))
    return text, prov


@dataclass
class VerifyResult:
    supports: bool
    confidence: float
    reasoning: str
    best_citation: Citation
    # Empty by default so existing call sites and tests that don't yet
    # populate doctrine continue to work unchanged. Populated by
    # ``verify_entitlement`` from ``retrieve_supporting_context`` when
    # the curriculum collection has matching chunks above threshold.
    supporting_doctrine: list[SupportingDoctrine] = field(default_factory=list)
    # Provenance is REQUIRED for every VerifyResult — the regression
    # test in tests/test_agent_provenance.py asserts this so a future
    # refactor cannot silently drop the audit trail. The short-circuit
    # paths (no chunks, bad JSON) still build a synthetic provenance
    # with call_kind="messages.create" and zero latency so the contract
    # holds without faking a Claude call that never happened.
    agent_provenance: AgentProvenance = field(
        default_factory=lambda: AgentProvenance(
            call_kind="messages.create",
            agent_backed=False,
            model=settings.claude_model,
            latency_ms=0,
        )
    )


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

    # Curriculum (CO 1-183 + specialized doctrine) is purely advisory: we
    # surface up to a few paragraphs to the model alongside the
    # authoritative chunks so it can reason with context, but the citation
    # contract is unchanged. Soft-fail on every error path so a missing
    # collection or a Qdrant outage never blocks the scan.
    try:
        doctrine_chunks = await asyncio.to_thread(
            retrieve_supporting_context,
            entitlement.title.en,
            topic_tags=[entitlement.category],
        )
    except Exception as exc:
        logger.warning(
            "supporting_doctrine_lookup_failed entitlement_id=%s exc=%s",
            entitlement.id,
            type(exc).__name__,
        )
        doctrine_chunks = []

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

    # Tag each chunk strictly: is_authoritative reflects only the language
    # provenance, never a fallback promotion. If no DE/FR/IT chunk was
    # retrieved, set translation_only=true on the envelope so the verifier
    # caps confidence and notes the missing original-language source. Once
    # Task #19 ingests DE Fedlex text, the same SRs will start surfacing
    # is_authoritative=true chunks automatically.
    chunk_payload: list[dict[str, Any]] = [
        {
            "text": c.text,
            "language": c.language,
            "score": round(c.score, 3),
            "is_authoritative": _is_authoritative_language(cit.sr_number, c.language),
        }
        for c in chunks
    ]
    translation_only = not any(c["is_authoritative"] for c in chunk_payload)
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

    # Doctrine payload is intentionally minimal — text + citation slug —
    # so the model treats it as a hint, not a citable source. The verifier
    # also re-states the policy in the SYSTEM prompt under "Supporting-
    # doctrine policy" to remove ambiguity.
    doctrine_payload = [
        {
            "source_doc": d.source_doc,
            "chapter": d.chapter,
            "section": d.section,
            "score": round(d.score, 3),
            "text": d.text,
        }
        for d in doctrine_chunks
    ]

    chunks_envelope = {
        "translation_only": translation_only,
        "chunks": chunk_payload,
        "supporting_doctrine": doctrine_payload,
    }
    chunks_block = (
        f"{_CHUNKS_OPEN}\n"
        f"{json.dumps(chunks_envelope, indent=2, ensure_ascii=False)}\n"
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

    text, provenance = await _call_claude(
        user_content, site=f"engine.verify:{entitlement.id}"
    )
    logger.info(
        "claude_verify entitlement_id=%s latency_ms=%d input_tokens=%d "
        "output_tokens=%d agent_backed=%s",
        entitlement.id,
        provenance.latency_ms,
        provenance.input_tokens,
        provenance.output_tokens,
        str(provenance.agent_backed).lower(),
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
            agent_provenance=provenance,
        )

    quote = " ".join(str(parsed.get("best_quote", "")).strip().split()[:14])
    top = chunks[0]
    confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
    # Hard cap on translation-only verifications: even if Claude ignores the
    # prompt instruction, the policy is enforced server-side.
    if translation_only and confidence > _TRANSLATION_ONLY_CONFIDENCE_CAP:
        logger.info(
            "claude_verify_capped entitlement_id=%s raw=%.2f cap=%.2f",
            entitlement.id,
            confidence,
            _TRANSLATION_ONLY_CONFIDENCE_CAP,
        )
        confidence = _TRANSLATION_ONLY_CONFIDENCE_CAP
    return VerifyResult(
        supports=bool(parsed.get("supports", False)),
        confidence=confidence,
        reasoning=str(parsed.get("reasoning", "")),
        best_citation=cit.model_copy(
            update={
                "quote_under_15_words": quote or cit.quote_under_15_words,
                "effective_date": top.effective_date or cit.effective_date,
                "score": top.score,
            }
        ),
        supporting_doctrine=[
            SupportingDoctrine(
                source_doc=d.source_doc,
                chapter=d.chapter,
                section=d.section,
                # Pydantic field is bounded [0, 1]; the curriculum retriever
                # already enforces score_threshold>=0, so clamp paranoia.
                score=max(0.0, min(1.0, d.score)),
            )
            for d in doctrine_chunks
        ],
        agent_provenance=provenance,
    )
