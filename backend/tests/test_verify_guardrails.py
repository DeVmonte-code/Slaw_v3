"""Anti-hallucination guardrail tests for the retrieval + verifier loop.

Covers Task #18:

(i)    Repealed-law clause is present in the Qdrant query filter.
(ii)   Wrong-canton chunks are excluded by the canton MatchAny clause.
(iii)  Sub-threshold retrieval short-circuits the verifier — no Claude call.
(iv)   DE chunk is presented to Claude as is_authoritative=true alongside an
       EN translation marked is_authoritative=false (DE-provenance SR).
(v)    EN-only retrieval keeps is_authoritative=false and sets
       translation_only=true on the envelope.
(vi)   Server-side cap clamps translation-only confidence to 0.75.
(vii)  Integration: retrieve_for_citation passes score_threshold to Qdrant,
       transforms payload (language + effective_date), and probes once for
       telemetry when the above-threshold response is empty.
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http import models as qmodels

from swiss_legal_api.engine import retrieval as retrieval_mod
from swiss_legal_api.engine import verify as verify_mod
from swiss_legal_api.engine.retrieval import (
    RetrievedChunk,
    _build_query_filter,
    retrieve_for_citation,
)
from swiss_legal_api.engine.verify import (
    _CHUNKS_CLOSE,
    _CHUNKS_OPEN,
    verify_entitlement,
)
from swiss_legal_api.schemas import AgentProvenance, Citation, ContextProfile, Entitlement


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


def _extract_chunks_envelope(user_content: str) -> dict[str, Any]:
    """Pull the JSON envelope (translation_only + chunks) from the user message."""
    start = user_content.index(_CHUNKS_OPEN) + len(_CHUNKS_OPEN)
    end = user_content.index(_CHUNKS_CLOSE)
    payload = json.loads(user_content[start:end].strip())
    assert isinstance(payload, dict) and "chunks" in payload
    return payload


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

    async def _fake_call_claude(
        user_content: str, *, site: str = ""
    ) -> tuple[str, AgentProvenance]:
        captured["content"] = user_content
        body = json.dumps(
            {
                "supports": True,
                "confidence": 0.8,
                "reasoning": "ok",
                "best_quote": "Test quote within fifteen words.",
            }
        )
        return body, AgentProvenance(
            call_kind="messages.create",
            agent_backed=False,
            model="claude-fake",
            latency_ms=1,
            input_tokens=50,
            output_tokens=20,
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    cit = _de_citation()
    result = await verify_entitlement(_entitlement(cit), _profile(), [])

    envelope = _extract_chunks_envelope(captured["content"])
    chunks = envelope["chunks"]
    assert envelope["translation_only"] is False
    assert len(chunks) == 2
    by_lang = {c["language"]: c for c in chunks}
    assert by_lang["de"]["is_authoritative"] is True
    assert by_lang["en"]["is_authoritative"] is False
    # Authoritative chunk is sent first so Claude reads it before the
    # translation aid.
    assert chunks[0]["language"] == "de"

    # best_citation surfaces the top chunk's effective_date and similarity score.
    assert result.best_citation.effective_date == date(1995, 1, 1)
    assert result.best_citation.score == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_translation_only_keeps_en_non_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(v) EN-only retrieval flags translation_only=true; EN stays non-authoritative.

    Required for Task #19 hand-off: when the DE Fedlex pipeline lands and
    DE chunks start being retrieved, the same SR will silently flip
    translation_only=false and is_authoritative=true on the new DE chunk.
    """
    en_only = RetrievedChunk(
        text="English Fedlex translation only.",
        score=0.82,
        language="en",
        effective_date=date(1912, 1, 1),
    )
    monkeypatch.setattr(
        verify_mod, "retrieve_for_citation", lambda *a, **k: [en_only]
    )

    captured: dict[str, str] = {}

    async def _fake_call_claude(
        user_content: str, *, site: str = ""
    ) -> tuple[str, AgentProvenance]:
        captured["content"] = user_content
        body = json.dumps(
            {
                "supports": True,
                "confidence": 0.7,
                "reasoning": "translation only — wording clear",
                "best_quote": "Translation supports the claim.",
            }
        )
        return body, AgentProvenance(
            call_kind="messages.create",
            agent_backed=False,
            model="claude-fake",
            latency_ms=1,
            input_tokens=40,
            output_tokens=15,
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    cit = Citation(
        sr_number="220",
        article="270a",
        language="en",
        quote_under_15_words="Quote in English.",
    )
    result = await verify_entitlement(_entitlement(cit), _profile(), [])

    envelope = _extract_chunks_envelope(captured["content"])
    assert envelope["translation_only"] is True
    assert len(envelope["chunks"]) == 1
    assert envelope["chunks"][0]["language"] == "en"
    assert envelope["chunks"][0]["is_authoritative"] is False
    # Verifier still ran (didn't short-circuit) and surfaced top chunk metadata.
    assert result.best_citation.score == pytest.approx(0.82)
    assert result.best_citation.effective_date == date(1912, 1, 1)


@pytest.mark.asyncio
async def test_translation_only_caps_confidence_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(vi) Server-side cap fires when Claude returns >0.75 on translation-only.

    Even if the model ignores the prompt cap, the policy is enforced in code.
    """
    en_only = RetrievedChunk(
        text="English Fedlex translation only.",
        score=0.82,
        language="en",
        effective_date=date(1912, 1, 1),
    )
    monkeypatch.setattr(
        verify_mod, "retrieve_for_citation", lambda *a, **k: [en_only]
    )

    async def _fake_call_claude(_user: str, *, site: str = "") -> tuple[str, AgentProvenance]:
        # Model misbehaves and returns 0.95 despite the prompt cap.
        body = json.dumps(
            {
                "supports": True,
                "confidence": 0.95,
                "reasoning": "ignored the cap",
                "best_quote": "Translation supports the claim.",
            }
        )
        return body, AgentProvenance(
            call_kind="messages.create",
            agent_backed=False,
            model="claude-fake",
            latency_ms=1,
            input_tokens=40,
            output_tokens=15,
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    cit = Citation(
        sr_number="220",
        article="270a",
        language="en",
        quote_under_15_words="Quote in English.",
    )
    result = await verify_entitlement(_entitlement(cit), _profile(), [])

    assert result.supports is True
    assert result.confidence == pytest.approx(0.75)


def test_retrieve_for_citation_integration_with_mocked_qdrant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(vii) End-to-end retrieval against a stubbed Qdrant client.

    Asserts that retrieve_for_citation:
      - passes ``score_threshold`` to ``query_points`` (source-side prune),
      - transforms point payloads into RetrievedChunk with language and
        effective_date,
      - drops sub-threshold points via the defense-in-depth client filter,
      - issues the no-threshold probe query exactly once when above-threshold
        retrieval is empty (so operators get a top_score telemetry line).
    """
    monkeypatch.setattr(retrieval_mod, "embed_query", lambda _q: [0.0] * 384)

    calls: list[dict[str, Any]] = []

    def make_response(points: list[Any]) -> SimpleNamespace:
        return SimpleNamespace(points=points)

    def stub_query_points(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        # First call carries score_threshold; return one above + one below
        # to exercise both Qdrant-side and client-side pruning paths.
        if "score_threshold" in kwargs and kwargs["score_threshold"] is not None:
            above = SimpleNamespace(
                score=0.91,
                payload={
                    "text": "Original German law text.",
                    "language": "de",
                    "effective_date": "1995-01-01T00:00:00Z",
                },
            )
            # Defense-in-depth: even if Qdrant accidentally returns a
            # below-threshold chunk, the client filter must drop it.
            below = SimpleNamespace(
                score=0.40,
                payload={
                    "text": "Should be dropped.",
                    "language": "de",
                    "effective_date": "1995-01-01T00:00:00Z",
                },
            )
            return make_response([above, below])
        # Probe query (no threshold) — used only for telemetry on empty above.
        return make_response([SimpleNamespace(score=0.42, payload=None)])

    fake_client = SimpleNamespace(query_points=stub_query_points)
    monkeypatch.setattr(retrieval_mod, "_client", lambda: fake_client)

    cit = _de_citation()
    result = retrieve_for_citation(cit, "training", profile_canton="ZH")

    # Source-side score_threshold was passed to Qdrant, populated from settings.
    assert calls, "expected at least one query_points call"
    assert calls[0]["score_threshold"] == retrieval_mod.settings.score_threshold
    # Filter built into the request includes the canton + repealed_date guards.
    flt = calls[0]["query_filter"]
    assert isinstance(flt, qmodels.Filter)

    # Only the above-threshold point survives, transformed correctly.
    assert len(result) == 1
    chunk = result[0]
    assert chunk.score == pytest.approx(0.91)
    assert chunk.language == "de"
    assert chunk.effective_date == date(1995, 1, 1)
    assert "Original German" in chunk.text
    # No probe call needed when above-threshold retrieval was non-empty.
    assert len(calls) == 1


def test_retrieve_for_citation_probes_for_telemetry_on_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Qdrant returns nothing above threshold, exactly one probe query
    (no threshold) is issued so operators see the actual top observed score."""
    monkeypatch.setattr(retrieval_mod, "embed_query", lambda _q: [0.0] * 384)

    calls: list[dict[str, Any]] = []

    def stub_query_points(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        if "score_threshold" in kwargs and kwargs["score_threshold"] is not None:
            return SimpleNamespace(points=[])
        # Probe response: return one low-similarity point for telemetry.
        return SimpleNamespace(
            points=[SimpleNamespace(score=0.31, payload=None)]
        )

    monkeypatch.setattr(
        retrieval_mod, "_client", lambda: SimpleNamespace(query_points=stub_query_points)
    )

    result = retrieve_for_citation(_de_citation(), "training", profile_canton="ZH")

    assert result == []
    # Two calls: the threshold-gated query + the no-threshold telemetry probe.
    assert len(calls) == 2
    assert calls[0]["score_threshold"] == retrieval_mod.settings.score_threshold
    assert "score_threshold" not in calls[1] or calls[1].get("score_threshold") is None
