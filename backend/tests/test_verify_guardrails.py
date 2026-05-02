"""Anti-hallucination guardrail tests for the retrieval + verifier loop.

Covers Task #18:

(i)   Repealed-law clause is present in the Qdrant query filter.
(ii)  Wrong-canton chunks are excluded by the canton MatchAny clause.
(iii) Sub-threshold retrieval short-circuits the verifier — no Claude call.
(iv)  DE chunk is presented to Claude as is_authoritative=true alongside an
      EN translation marked is_authoritative=false (DE-provenance SR).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http import models as qmodels

from swiss_legal_api.engine import verify as verify_mod
from swiss_legal_api.engine.retrieval import (
    RetrievedChunk,
    _build_query_filter,
)
from swiss_legal_api.engine.verify import (
    _CHUNKS_CLOSE,
    _CHUNKS_OPEN,
    verify_entitlement,
)
from swiss_legal_api.schemas import Citation, ContextProfile, Entitlement


def _de_citation() -> Citation:
    return Citation(
        sr_number="642.11",
        article="33",
        paragraph="1",
        language="de",
        quote_under_15_words="Test quote in German for verification.",
    )


def _profile(canton: str = "ZH") -> ContextProfile:
    return ContextProfile.model_validate(
        {
            "canton": canton,
            "employment_status": "employee_full_time",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "80_120k",
        }
    )


def _entitlement(citation: Citation) -> Entitlement:
    return Entitlement.model_validate(
        {
            "id": "test_ent",
            "title": {"de": "Test", "en": "Test entitlement"},
            "category": "tax_deduction",
            "jurisdiction": "CH",
            "source_citations": [citation.model_dump(mode="json")],
            "trigger": {"all": []},
            "estimated_value_chf": {"min": 0, "max": 100, "per": "year"},
            "required_action": "tax_declaration_field",
        }
    )


def _extract_chunks_block(user_content: str) -> list[dict[str, Any]]:
    """Pull the JSON chunk array out of the verifier's user-message block."""
    start = user_content.index(_CHUNKS_OPEN) + len(_CHUNKS_OPEN)
    end = user_content.index(_CHUNKS_CLOSE)
    return json.loads(user_content[start:end].strip())


def test_filter_includes_repealed_date_clause() -> None:
    """(i) A nested should-clause excludes repealed law from retrieval."""
    flt = _build_query_filter(_de_citation(), "ZH", date(2026, 5, 2))

    nested = [m for m in flt.must if isinstance(m, qmodels.Filter)]
    assert nested, "expected a nested Filter for the repealed_date clause"

    # Three-way disjunction: missing field, explicit null, OR future date.
    found_repealed_clause = False
    for nest in nested:
        for c in nest.should or []:
            if isinstance(c, qmodels.IsEmptyCondition) and c.is_empty.key == "repealed_date":
                found_repealed_clause = True
            if isinstance(c, qmodels.IsNullCondition) and c.is_null.key == "repealed_date":
                found_repealed_clause = True
            if (
                isinstance(c, qmodels.FieldCondition)
                and c.key == "repealed_date"
                and c.range is not None
                and c.range.gt is not None
            ):
                found_repealed_clause = True
    assert found_repealed_clause

    # And the effective_date <= today gate is in the top-level must clauses.
    eff_conds = [
        m
        for m in flt.must
        if isinstance(m, qmodels.FieldCondition) and m.key == "effective_date"
    ]
    assert len(eff_conds) == 1
    assert eff_conds[0].range is not None
    assert eff_conds[0].range.lte is not None
    # qdrant-client parses the RFC3339 string into a datetime; either form is fine.
    assert "2026-05-02" in str(eff_conds[0].range.lte)


def test_filter_includes_canton_match_any() -> None:
    """(ii) The canton clause accepts {profile_canton, "CH"} only."""
    flt = _build_query_filter(_de_citation(), "ZH", date(2026, 5, 2))
    canton_conds = [
        m
        for m in flt.must
        if isinstance(m, qmodels.FieldCondition) and m.key == "canton"
    ]
    assert len(canton_conds) == 1
    assert isinstance(canton_conds[0].match, qmodels.MatchAny)
    assert set(canton_conds[0].match.any) == {"ZH", "CH"}


@pytest.mark.asyncio
async def test_subthreshold_short_circuits_without_claude_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(iii) Empty retrieval → hard refusal, no Claude tokens spent."""
    monkeypatch.setattr(
        verify_mod, "retrieve_for_citation", lambda *a, **k: []
    )
    sentinel = AsyncMock()
    monkeypatch.setattr(verify_mod, "_call_claude", sentinel)

    cit = _de_citation()
    ent = _entitlement(cit)

    result = await verify_entitlement(ent, _profile(), [])

    assert result.supports is False
    assert result.confidence == 0.0
    assert "threshold" in result.reasoning.lower()
    sentinel.assert_not_awaited()
    sentinel.assert_not_called()


@pytest.mark.asyncio
async def test_de_chunk_marked_authoritative_for_de_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(iv) DE chunk is_authoritative=true; EN translation is_authoritative=false."""
    de_chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.91,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    en_chunk = RetrievedChunk(
        text="English Fedlex translation.",
        score=0.78,
        language="en",
        effective_date=date(1995, 1, 1),
    )

    monkeypatch.setattr(
        verify_mod,
        "retrieve_for_citation",
        lambda *a, **k: [de_chunk, en_chunk],
    )

    captured: dict[str, str] = {}

    async def _fake_call_claude(user_content: str) -> tuple[str, dict[str, int]]:
        captured["content"] = user_content
        body = json.dumps(
            {
                "supports": True,
                "confidence": 0.8,
                "reasoning": "ok",
                "best_quote": "Test quote within fifteen words.",
            }
        )
        return body, {"input_tokens": 50, "output_tokens": 20}

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    cit = _de_citation()
    result = await verify_entitlement(_entitlement(cit), _profile(), [])

    chunks = _extract_chunks_block(captured["content"])
    assert len(chunks) == 2
    by_lang = {c["language"]: c for c in chunks}
    assert by_lang["de"]["is_authoritative"] is True
    assert by_lang["en"]["is_authoritative"] is False

    # best_citation surfaces the top chunk's effective_date and similarity score.
    assert result.best_citation.effective_date == date(1995, 1, 1)
    assert result.best_citation.score == pytest.approx(0.91)
