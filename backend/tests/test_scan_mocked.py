"""Mocked end-to-end test for the scan pipeline.

Uses respx to stub Anthropic's /v1/messages endpoint and monkey-patches the
Qdrant retrieval helper so the test runs offline — no ANTHROPIC_API_KEY,
no QDRANT_URL, no embedder load. Verifies that scan_profile produces a
valid BenefitReport with the expected shape.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from swiss_legal_api.catalog import load_catalog
from swiss_legal_api.engine import retrieval as retrieval_mod
from swiss_legal_api.engine import verify as verify_mod
from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.schemas import ContextProfile


def _luis() -> ContextProfile:
    fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "luis_profile.json"
    return ContextProfile.model_validate(json.loads(fixtures.read_text()))


def _stub_retrieve(
    citation: Any,
    extra_query: str,
    profile_canton: str = "CH",
    score_threshold: float | None = None,
    today: Any = None,
    caller_context: str = "",
) -> list[retrieval_mod.RetrievedChunk]:
    del extra_query, profile_canton, score_threshold, today, caller_context
    return [
        retrieval_mod.RetrievedChunk(
            text=f"[stub] verbatim text for SR {citation.sr_number} Art. {citation.article}",
            score=0.91,
            language=getattr(citation, "language", "de"),
            effective_date=None,
        )
    ]


@pytest.fixture
def patched_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retrieval_mod, "retrieve_for_citation", _stub_retrieve)
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", _stub_retrieve)


@pytest.mark.asyncio
async def test_scan_with_mocked_anthropic(
    patched_retrieval: None,
) -> None:
    canned = {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": "claude-stub",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 40},
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "supports": True,
                        "confidence": 0.85,
                        "reasoning": "Stubbed verification — text supports the claim.",
                        "best_quote": "Stubbed verbatim Fedlex quote.",
                    }
                ),
            }
        ],
    }

    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=canned)
        )
        report = await run_benefit_scan(_luis(), load_catalog())

    assert report.profile_hash and len(report.profile_hash) == 16
    assert report.generated_at.endswith("Z")
    assert isinstance(report.benefits, list)
    assert len(report.benefits) >= 5, (
        f"Expected ≥5 benefits for the Luis fixture, got {len(report.benefits)}: "
        f"{[b.entitlement_id for b in report.benefits]}"
    )

    for b in report.benefits:
        assert 0.0 <= b.confidence <= 1.0
        assert b.citations, f"benefit {b.entitlement_id} has no citations"
        for cit in b.citations:
            assert cit.sr_number
            assert cit.article
            assert len(cit.quote_under_15_words.split()) <= 15


@pytest.mark.asyncio
async def test_scan_marks_low_confidence_as_suppressed(
    patched_retrieval: None,
) -> None:
    canned = {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": "claude-stub",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 30},
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "supports": False,
                        "confidence": 0.1,
                        "reasoning": "Retrieved text does not support the claim.",
                        "best_quote": "n/a",
                    }
                ),
            }
        ],
    }

    with respx.mock(assert_all_called=False) as router:
        router.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=canned)
        )
        report = await run_benefit_scan(_luis(), load_catalog())

    assert report.benefits == []
    assert report.suppressed_count >= 5
