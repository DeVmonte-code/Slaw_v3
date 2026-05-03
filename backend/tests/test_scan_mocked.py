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
from swiss_legal_api.engine import scan as scan_mod
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
    # Normal path: with no placeholder rows in the seed (the backfill
    # follow-up has either landed or never staged any), the guard is a
    # no-op and the counter stays at zero.
    assert report.pending_corpus_backfill == 0

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


def test_pending_corpus_articles_loads_real_seed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for ``_LAW_ARTICLES_PATH`` resolution.

    The loader must read the same seed/law_articles.json the seeder uses,
    not a phantom path one directory up or down. We point the constant at
    a temp file with two placeholder rows + one real row, clear the
    lru_cache, and check the loader returns exactly the placeholder keys.
    A wrong ``parents[N]`` index would surface here as an empty set.
    """
    seed = tmp_path / "law_articles.json"
    seed.write_text(
        json.dumps(
            [
                {
                    "sr_number": "141.0",
                    "article": "9",
                    "paragraph": "1",
                    "language": "de",
                    "text": "__PENDING_FEDLEX_VERBATIM__",
                    "canton": "CH",
                    "effective_date": "2018-01-01",
                    "repealed_date": None,
                },
                {
                    "sr_number": "142.20",
                    "article": "43",
                    "paragraph": "1",
                    "language": "de",
                    "text": "TODO: __PENDING_FEDLEX_VERBATIM__ (backfill)",
                    "canton": "CH",
                    "effective_date": "2008-01-01",
                    "repealed_date": None,
                },
                {
                    "sr_number": "220",
                    "article": "1",
                    "paragraph": "1",
                    "language": "de",
                    "text": "Real legal text — must NOT be flagged.",
                    "canton": "CH",
                    "effective_date": "1912-01-01",
                    "repealed_date": None,
                },
            ]
        )
    )
    monkeypatch.setattr(scan_mod, "_LAW_ARTICLES_PATH", seed)
    scan_mod._pending_corpus_articles.cache_clear()
    try:
        pending = scan_mod._pending_corpus_articles()
    finally:
        scan_mod._pending_corpus_articles.cache_clear()

    assert pending == frozenset({("141.0", "9"), ("142.20", "43")})


def test_all_citations_pending_requires_every_citation_to_be_pending() -> None:
    """Locks in the rule: skip only when EVERY citation is a placeholder.

    A mixed entitlement (one pending citation + one real citation) must
    still be verified — Claude can produce a meaningful verdict from the
    real article alone, so suppressing it would silently regress recall.
    """
    catalog = load_catalog()
    by_id = {e.id: e for e in catalog}
    # `family_reunification_right` cites a single article (SR 142.20 / 43).
    # Build a synthetic two-citation entitlement by appending a real
    # citation to verify the all-citations rule on multi-citation inputs.
    base = by_id["family_reunification_right"]
    real_citation = by_id["unemployment_insurance_entitlement"].source_citations[0]
    mixed = base.model_copy(update={"source_citations": [base.source_citations[0], real_citation]})
    pending_only_one = frozenset(
        {(base.source_citations[0].sr_number, base.source_citations[0].article)}
    )

    # Single-citation, fully pending → skip.
    assert scan_mod._all_citations_pending(base, pending_only_one) is True
    # Mixed (one pending, one real) → DO NOT skip.
    assert scan_mod._all_citations_pending(mixed, pending_only_one) is False
    # Empty pending set → never skip.
    assert scan_mod._all_citations_pending(base, frozenset()) is False


def test_pending_corpus_articles_resolves_against_real_repo_seed() -> None:
    """The constant must point at backend/seed/law_articles.json so the
    guard sees the same file the seeder filters on. If a future refactor
    moves scan.py and forgets to bump ``parents[N]``, this test fails
    even when no placeholders are currently in the seed.
    """
    expected = Path(__file__).resolve().parent.parent / "seed" / "law_articles.json"
    assert expected == scan_mod._LAW_ARTICLES_PATH
    assert scan_mod._LAW_ARTICLES_PATH.exists(), (
        f"seed file missing at {scan_mod._LAW_ARTICLES_PATH}; the placeholder "
        "guard would silently no-op in production."
    )


@pytest.mark.asyncio
async def test_scan_skips_entitlements_with_pending_corpus_backfill(
    patched_retrieval: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skip path: when every cited article of an entitlement is still a
    ``__PENDING_FEDLEX_VERBATIM__`` placeholder in seed/law_articles.json,
    ``run_benefit_scan`` must NOT call Claude for it and must increment the
    ``pending_corpus_backfill`` counter on the report instead.

    We pick ``fundamental_error_rescission`` (cites SR 220 Art. 24) and
    ``tort_claim_placeholder`` (cites SR 220 Art. 41) because both have an
    ``{"all": []}`` trigger that always matches, so the only reason they
    could be missing from the report is the new placeholder guard.
    """
    pending = frozenset({("220", "24"), ("220", "41")})
    monkeypatch.setattr(scan_mod, "_pending_corpus_articles", lambda: pending)

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
                        "reasoning": "Stubbed verification.",
                        "best_quote": "Stubbed verbatim Fedlex quote.",
                    }
                ),
            }
        ],
    }

    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=canned)
        )
        report = await run_benefit_scan(_luis(), load_catalog())

    benefit_ids = {b.entitlement_id for b in report.benefits}
    # The two placeholder-only entitlements must be absent from the
    # verified output...
    assert "fundamental_error_rescission" not in benefit_ids
    assert "tort_claim_placeholder" not in benefit_ids
    # ...counted on the new dashboard field instead of the suppressed
    # bucket (which is reserved for low-confidence Claude verdicts)...
    assert report.pending_corpus_backfill == 2
    # ...and other entitlements were still verified normally, so Claude
    # was called at least once (proving the guard is targeted, not a
    # blanket skip).
    assert route.call_count >= 1
    assert len(report.benefits) >= 1
