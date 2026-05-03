"""Curriculum ingest + verifier-wiring tests for Task #20.

Covers:

  * Chunker determinism — same input → byte-identical output, monotonic
    chunk_index.
  * Stable UUID5 IDs over (source_doc, page, chunk_index) so re-seeding is
    a Qdrant upsert in place rather than churning IDs.
  * ``retrieve_supporting_context`` applies the topic_tag MatchAny filter
    when tags are passed, and short-circuits to [] when Qdrant is not
    configured (offline path).
  * Soft-fail when the curriculum collection is missing (Qdrant raises) —
    deployments without seeded PDFs must still return a Benefit, just
    without doctrine.
  * Verifier wires doctrine into the envelope sent to Claude.
  * VerifyResult.supporting_doctrine threads through ``run_benefit_scan``
    onto the Benefit.

Every test is offline. The Qdrant client is monkey-patched and the
curriculum module's ``settings.qdrant_url`` is forced to a non-empty
sentinel for the tests that need to exercise the live-path code.
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client.http import models as qmodels

from swiss_legal_api.engine import retrieval as retrieval_mod
from swiss_legal_api.engine import scan as scan_mod
from swiss_legal_api.engine import verify as verify_mod
from swiss_legal_api.engine.retrieval import (
    RetrievedChunk,
    SupportingChunk,
    retrieve_supporting_context,
)
from swiss_legal_api.engine.verify import (
    _CHUNKS_CLOSE,
    _CHUNKS_OPEN,
    verify_entitlement,
)
from swiss_legal_api.schemas import (
    AgentProvenance,
    Benefit,
    Citation,
    ContextProfile,
    Entitlement,
    SupportingDoctrine,
)
from swiss_legal_api.seeding.curriculum_chunker import (
    CurriculumChunk,
    chunk_pages,
)
from swiss_legal_api.seeding.seed_curriculum import _stable_id


def _fake_provenance() -> AgentProvenance:
    return AgentProvenance(
        call_kind="messages.create",
        agent_backed=False,
        model="claude-fake",
        latency_ms=1,
        input_tokens=50,
        output_tokens=20,
    )

# ---------------------------------------------------------------------------
# Chunker determinism + ID stability
# ---------------------------------------------------------------------------


_PAGE_1 = (
    "Article 1. A contract is concluded by mutual assent of the parties. "
    "The assent may be express or implied from conduct. "
    "Silence does not amount to assent unless circumstances dictate otherwise.\n\n"
    "Article 2. Where the parties agree on the essentialia negotii, the "
    "contract is formed even if subsidiary points remain reserved. "
    "Subsidiary points must be settled in accordance with the nature of "
    "the transaction."
)
_PAGE_2 = (
    "Article 3. An offer with a time limit binds the offeror until expiry. "
    "Acceptance must reach the offeror within that time. "
    "An acceptance arriving late is a new offer, unless the offeror notifies "
    "the late acceptor without delay."
)


def test_chunker_is_deterministic() -> None:
    """Same inputs -> identical output. UUID5 stable IDs depend on this."""
    a = chunk_pages(
        "co_articles_1_183",
        [_PAGE_1, _PAGE_2],
        language="en",
        topic_tags=("contracts",),
        max_words=40,
        overlap_words=5,
    )
    b = chunk_pages(
        "co_articles_1_183",
        [_PAGE_1, _PAGE_2],
        language="en",
        topic_tags=("contracts",),
        max_words=40,
        overlap_words=5,
    )
    assert a == b
    assert a, "expected at least one chunk from non-empty pages"


def test_chunk_index_resets_per_page_and_is_monotonic() -> None:
    """chunk_index must reset to 0 on each new page and only ever increase
    within a page so the (source_doc, page, chunk_index) ID tuple is unique."""
    chunks = chunk_pages(
        "co_articles_1_183",
        [_PAGE_1, _PAGE_2],
        max_words=30,
        overlap_words=4,
    )
    by_page: dict[int, list[int]] = {}
    for c in chunks:
        by_page.setdefault(c.page, []).append(c.chunk_index)
    for page, indices in by_page.items():
        assert indices[0] == 0, f"page {page} did not start at chunk_index 0"
        assert indices == sorted(indices), (
            f"page {page} chunk_index not monotonic: {indices}"
        )
        assert len(indices) == len(set(indices)), (
            f"page {page} has duplicate chunk_index"
        )


def test_stable_id_round_trips_per_identity_tuple() -> None:
    """``_stable_id`` is a pure function of (source_doc, page, chunk_index)."""
    same_a = CurriculumChunk(
        source_doc="co_articles_1_183", page=12, chunk_index=3, text="x"
    )
    same_b = CurriculumChunk(
        source_doc="co_articles_1_183",
        page=12,
        chunk_index=3,
        text="completely different text but same identity",
        chapter="Chapter 2",
        topic_tags=("contracts",),
    )
    different = CurriculumChunk(
        source_doc="co_articles_1_183", page=12, chunk_index=4, text="x"
    )
    assert _stable_id(same_a) == _stable_id(same_b)
    assert _stable_id(same_a) != _stable_id(different)


# ---------------------------------------------------------------------------
# retrieve_supporting_context — filter shape + soft-fail paths
# ---------------------------------------------------------------------------


class _StubQdrant:
    """Captures the last ``query_points`` call so we can assert the filter."""

    def __init__(
        self,
        *,
        points: list[Any] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._points = points or []
        self._raise_exc = raise_exc
        self.last_call: dict[str, Any] | None = None

    def query_points(self, **kwargs: Any) -> Any:
        self.last_call = kwargs
        if self._raise_exc is not None:
            raise self._raise_exc
        return SimpleNamespace(points=self._points)


def _qdrant_point(
    *,
    text: str = "Doctrinal paragraph here.",
    score: float = 0.71,
    source_doc: str = "co_articles_1_183",
    chapter: str | None = "Chapter 2: Errors",
    section: str | None = "§ 12 — Error of fact",
    page: int = 12,
) -> Any:
    return SimpleNamespace(
        score=score,
        payload={
            "text": text,
            "source_doc": source_doc,
            "chapter": chapter,
            "section": section,
            "page": page,
        },
    )


def test_retrieve_supporting_context_short_circuits_when_qdrant_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Qdrant URL -> empty list, no embedder cold-start, no client call."""
    monkeypatch.setattr(retrieval_mod.settings, "qdrant_url", "")
    # Sentinel — fail loudly if the function tried to embed or call Qdrant.
    def _boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("must not be called when qdrant_url is empty")

    monkeypatch.setattr(retrieval_mod, "embed_query", _boom)
    monkeypatch.setattr(retrieval_mod, "_client", _boom)

    assert retrieve_supporting_context("anything", topic_tags=["contracts"]) == []


def test_retrieve_supporting_context_applies_topic_tag_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``topic_tags=[...]`` -> a MatchAny filter on ``topic_tags`` is sent."""
    monkeypatch.setattr(retrieval_mod.settings, "qdrant_url", "https://qdrant.example")
    monkeypatch.setattr(retrieval_mod.settings, "curriculum_collection", "co_curriculum")
    monkeypatch.setattr(retrieval_mod, "embed_query", lambda _t: [0.0] * 384)

    stub = _StubQdrant(points=[_qdrant_point()])
    monkeypatch.setattr(retrieval_mod, "_client", lambda: stub)

    out = retrieve_supporting_context(
        "Tenant deposit refund",
        topic_tags=["tenancy_right", "contracts"],
        top_k=2,
        score_threshold=0.4,
    )

    assert len(out) == 1
    assert isinstance(out[0], SupportingChunk)
    assert out[0].source_doc == "co_articles_1_183"
    assert out[0].chapter == "Chapter 2: Errors"
    assert out[0].section == "§ 12 — Error of fact"
    assert out[0].page == 12
    assert out[0].score == pytest.approx(0.71)

    assert stub.last_call is not None
    assert stub.last_call["collection_name"] == "co_curriculum"
    assert stub.last_call["limit"] == 2
    assert stub.last_call["score_threshold"] == 0.4
    flt = stub.last_call["query_filter"]
    assert isinstance(flt, qmodels.Filter)
    assert flt.must is not None and len(flt.must) == 1
    cond = flt.must[0]
    assert isinstance(cond, qmodels.FieldCondition)
    assert cond.key == "topic_tags"
    assert isinstance(cond.match, qmodels.MatchAny)
    assert set(cond.match.any) == {"tenancy_right", "contracts"}


def test_retrieve_supporting_context_no_filter_when_no_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No topic_tags -> ``query_filter=None`` (don't accidentally exclude
    chunks that simply have no tags)."""
    monkeypatch.setattr(retrieval_mod.settings, "qdrant_url", "https://qdrant.example")
    monkeypatch.setattr(retrieval_mod.settings, "curriculum_collection", "co_curriculum")
    monkeypatch.setattr(retrieval_mod, "embed_query", lambda _t: [0.0] * 384)
    stub = _StubQdrant(points=[])
    monkeypatch.setattr(retrieval_mod, "_client", lambda: stub)

    assert retrieve_supporting_context("anything") == []
    assert stub.last_call is not None
    assert stub.last_call["query_filter"] is None


def test_retrieve_supporting_context_soft_fails_when_collection_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing collection -> Qdrant raises -> [] + warning, never propagates."""
    monkeypatch.setattr(retrieval_mod.settings, "qdrant_url", "https://qdrant.example")
    monkeypatch.setattr(retrieval_mod.settings, "curriculum_collection", "co_curriculum")
    monkeypatch.setattr(retrieval_mod, "embed_query", lambda _t: [0.0] * 384)

    stub = _StubQdrant(raise_exc=RuntimeError("collection 'co_curriculum' not found"))
    monkeypatch.setattr(retrieval_mod, "_client", lambda: stub)

    with caplog.at_level("WARNING", logger=retrieval_mod.__name__):
        out = retrieve_supporting_context("query", topic_tags=["contracts"])
    assert out == []
    assert any(
        "curriculum_retrieval_unavailable" in r.message for r in caplog.records
    ), "expected a curriculum_retrieval_unavailable WARNING"


# ---------------------------------------------------------------------------
# Verifier + scan wiring
# ---------------------------------------------------------------------------


def _de_citation() -> Citation:
    return Citation(
        sr_number="220",
        article="1",
        paragraph="1",
        language="de",
        quote_under_15_words="Der Vertrag kommt durch übereinstimmende Willensäusserung zustande.",
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
            "id": "test_co_ent",
            "title": {"de": "Vertrag", "en": "Contract entitlement"},
            "category": "tenancy_right",
            "jurisdiction": "CH",
            "source_citations": [citation.model_dump(mode="json")],
            "trigger": {"all": []},
            "estimated_value_chf": {"min": 0, "max": 100, "per": "year"},
            "required_action": "claim_letter_to_landlord",
        }
    )


def _extract_envelope(user_content: str) -> dict[str, Any]:
    start = user_content.index(_CHUNKS_OPEN) + len(_CHUNKS_OPEN)
    end = user_content.index(_CHUNKS_CLOSE)
    payload = json.loads(user_content[start:end].strip())
    assert isinstance(payload, dict)
    return payload


@pytest.mark.asyncio
async def test_verifier_envelope_includes_supporting_doctrine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When curriculum returns chunks, they appear in the envelope under
    ``supporting_doctrine`` (advisory only) — chunks themselves are still
    the SR/article authority."""
    de_chunk = RetrievedChunk(
        text="Der Vertrag kommt durch übereinstimmende Willensäusserung zustande.",
        score=0.92,
        language="de",
        effective_date=date(1912, 1, 1),
    )
    monkeypatch.setattr(
        verify_mod, "retrieve_for_citation", lambda *a, **k: [de_chunk]
    )
    doctrine = [
        SupportingChunk(
            text="In Swiss contract doctrine, mutual assent need not be express.",
            score=0.66,
            source_doc="co_articles_1_183",
            chapter="Chapter 1: Formation",
            page=4,
        ),
    ]
    monkeypatch.setattr(
        verify_mod, "retrieve_supporting_context", lambda *a, **k: doctrine
    )

    captured: dict[str, str] = {}

    async def _fake_call_claude(content: str, *, site: str = "") -> tuple[str, AgentProvenance]:
        captured["content"] = content
        body = json.dumps(
            {
                "supports": True,
                "confidence": 0.83,
                "reasoning": "Article supports the claimed entitlement.",
                "best_quote": "Der Vertrag kommt durch übereinstimmende Willensäusserung.",
            }
        )
        return body, _fake_provenance()

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    cit = _de_citation()
    result = await verify_entitlement(_entitlement(cit), _profile(), [])

    envelope = _extract_envelope(captured["content"])
    assert "supporting_doctrine" in envelope
    sd = envelope["supporting_doctrine"]
    assert isinstance(sd, list) and len(sd) == 1
    assert sd[0]["source_doc"] == "co_articles_1_183"
    assert sd[0]["chapter"] == "Chapter 1: Formation"
    assert "Swiss contract doctrine" in sd[0]["text"]

    # SR + article authority is unchanged — citation contract preserved.
    assert result.supports is True
    assert result.best_citation.sr_number == "220"
    assert result.best_citation.article == "1"

    # And the doctrine is exposed on the VerifyResult for ``scan`` to pipe
    # through to the Benefit.
    assert len(result.supporting_doctrine) == 1
    sd_obj = result.supporting_doctrine[0]
    assert isinstance(sd_obj, SupportingDoctrine)
    assert sd_obj.source_doc == "co_articles_1_183"
    assert sd_obj.chapter == "Chapter 1: Formation"
    assert 0.0 <= sd_obj.score <= 1.0


@pytest.mark.asyncio
async def test_verifier_works_when_curriculum_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No doctrine retrieved -> envelope still has supporting_doctrine=[]
    and verifier completes normally. This is the steady-state for any
    deployment that hasn't seeded PDFs yet."""
    de_chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.88,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    monkeypatch.setattr(
        verify_mod, "retrieve_for_citation", lambda *a, **k: [de_chunk]
    )
    monkeypatch.setattr(
        verify_mod, "retrieve_supporting_context", lambda *a, **k: []
    )

    captured: dict[str, str] = {}

    async def _fake_call_claude(content: str, *, site: str = "") -> tuple[str, AgentProvenance]:
        captured["content"] = content
        return (
            json.dumps(
                {
                    "supports": True,
                    "confidence": 0.8,
                    "reasoning": "ok",
                    "best_quote": "Test quote.",
                }
            ),
            _fake_provenance(),
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    result = await verify_entitlement(_entitlement(_de_citation()), _profile(), [])
    envelope = _extract_envelope(captured["content"])
    assert envelope["supporting_doctrine"] == []
    assert result.supports is True
    assert result.supporting_doctrine == []


@pytest.mark.asyncio
async def test_verifier_soft_fails_on_doctrine_lookup_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if ``retrieve_supporting_context`` itself raises, the verifier
    must not blow up — log and continue with empty doctrine."""
    de_chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.88,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    monkeypatch.setattr(
        verify_mod, "retrieve_for_citation", lambda *a, **k: [de_chunk]
    )

    def _boom(*_a: Any, **_k: Any) -> list[SupportingChunk]:
        raise RuntimeError("qdrant cluster 503")

    monkeypatch.setattr(verify_mod, "retrieve_supporting_context", _boom)

    async def _fake_call_claude(_content: str, *, site: str = "") -> tuple[str, AgentProvenance]:
        return (
            json.dumps(
                {
                    "supports": True,
                    "confidence": 0.8,
                    "reasoning": "ok",
                    "best_quote": "Test quote.",
                }
            ),
            _fake_provenance(),
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    result = await verify_entitlement(_entitlement(_de_citation()), _profile(), [])
    assert result.supports is True
    assert result.supporting_doctrine == []


@pytest.mark.asyncio
async def test_supporting_doctrine_threads_through_to_benefit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full scan: doctrine survives ``run_benefit_scan`` onto Benefit.

    Validates the contract surfaced by the API: the JSON returned by /scan
    carries ``benefits[].supporting_doctrine`` populated end-to-end.
    """
    cit = _de_citation()
    ent = _entitlement(cit)

    # Pretend the catalog has just this one entitlement and that triggers
    # match (empty trigger evaluates true). Verifier returns supports=true.
    fake_doctrine = [
        SupportingDoctrine(
            source_doc="co_articles_1_183",
            chapter="Chapter 1: Formation",
            score=0.71,
        ),
    ]
    fake_result = verify_mod.VerifyResult(
        supports=True,
        confidence=0.9,
        reasoning="Article 1 directly supports contract formation by mutual assent.",
        best_citation=cit,
        supporting_doctrine=fake_doctrine,
    )

    async def _fake_verify(
        _e: Entitlement,
        _p: ContextProfile,
        _ev: list[Any],
        user_id: str = "anonymous",
    ) -> verify_mod.VerifyResult:
        return fake_result

    monkeypatch.setattr(scan_mod, "verify_entitlement", _fake_verify)

    report = await scan_mod.run_benefit_scan(_profile(), [ent])
    assert len(report.benefits) == 1
    benefit = report.benefits[0]
    assert isinstance(benefit, Benefit)
    assert len(benefit.supporting_doctrine) == 1
    assert benefit.supporting_doctrine[0].source_doc == "co_articles_1_183"
    assert benefit.supporting_doctrine[0].chapter == "Chapter 1: Formation"
    assert benefit.supporting_doctrine[0].score == pytest.approx(0.71)

    # Citation contract is unchanged — doctrine is *additive*, never a
    # replacement for SR + article authority.
    assert benefit.citations[0].sr_number == "220"
    assert benefit.citations[0].article == "1"
