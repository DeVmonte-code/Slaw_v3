# B6 — Verification Service

**Status:** ✅ Complete  
**Tests:** mypy strict + ruff clean (no fast-only tests; requires live LLM)

## Purpose
LLM-in-the-loop verifier that sends retrieved article text to Claude and asks for a confidence score + narrative for each candidate entitlement.

## Files Created
| File | Purpose |
|---|---|
| `src/swiss_legal_api/engine/verify.py` | `VerifyResult`, `verify_entitlement()` |

## verify_entitlement() Flow
1. Calls `retrieve_for_citation()` for each citation on the entitlement (up to first 2)
2. Assembles a structured prompt with the entitlement title, profile JSON, retrieved article text, and instructions
3. Calls Claude via `AsyncAnthropic.messages.create()` (model from `settings.claude_model`)
4. Parses the JSON response block (`{"confidence": 0.0–1.0, "narrative": "..."}`)
5. Returns `VerifyResult(confidence, narrative, citations_used)`
6. Falls back to `confidence=0.0, narrative="parse error"` on malformed JSON

## Prompt Design
- SYSTEM: defines strict response contract (JSON only, no disclaimers, cite SR, keep quotes ≤15 words)
- USER: includes `Profile`, `Entitlement`, and up to 6 retrieved article excerpts
- `max_tokens=500`

## Key Implementation Notes
- `from typing import Any` required; parameter typed as `list[dict[str, Any]]`
- SYSTEM string lines kept ≤100 chars (ruff E501 enforcement)
- Function is `async` — called from the scan orchestrator via `asyncio.gather()`

## Acceptance Criteria — All Met
- mypy strict clean ✅
- ruff clean ✅
