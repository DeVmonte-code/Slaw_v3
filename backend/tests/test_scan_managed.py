"""Managed-agents scan-driver tests (Task #36).

Asserts that ``run_benefit_scan`` opens at most ONE managed session
per request and that the agent's batched JSON reply is parsed back into
the existing ``BenefitReport`` shape — without changing the schema or
the local-path behaviour the rest of the test suite still exercises.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from swiss_legal_api.catalog import load_catalog
from swiss_legal_api.engine import scan as scan_mod
from swiss_legal_api.engine import verify as verify_mod
from swiss_legal_api.engine.retrieval import RetrievedChunk
from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.schemas import AgentProvenance, ContextProfile


def _luis() -> ContextProfile:
    fx = Path(__file__).resolve().parent.parent / "fixtures" / "luis_profile.json"
    return ContextProfile.model_validate(json.loads(fx.read_text()))


def _stub_chunk(citation: Any, *args: Any, **kwargs: Any) -> list[RetrievedChunk]:
    """Always-resolves retrieval probe used by the resolve-citation path."""
    return [
        RetrievedChunk(
            text=f"[stub] SR {citation.sr_number} Art. {citation.article}",
            score=0.92,
            language=getattr(citation, "language", "de"),
            effective_date=None,
        )
    ]


def _empty_chunks(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
    return []


def _make_provenance(*, mcp_calls: int, tool_calls: int = 0) -> AgentProvenance:
    return AgentProvenance(
        call_kind="sessions.events",
        agent_backed=(mcp_calls + tool_calls) > 0,
        model="claude-stub",
        latency_ms=12,
        agent_id="agent_test",
        agent_version=1,
        session_id="sess_managed_scan",
        environment_id="env_test",
        tools_offered=[
            "agent_toolset_20260401",
            "swiss-law-retrieval-mcp",
            "swiss-contract-tools-mcp",
        ],
        tool_use_count=tool_calls,
        mcp_tool_use_count=mcp_calls,
        mcp_servers_invoked=(
            ["swiss-contract-tools-mcp"] if mcp_calls else []
        ),
    )


@pytest.fixture
def force_managed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin settings so the agent driver branch is selected."""
    monkeypatch.setattr(scan_mod.settings, "use_managed_agents", True)
    # The driver itself doesn't read these (run_session is faked) but
    # _verify_via_managed_agent's hard gate would if a regression
    # accidentally routed through the per-entitlement path.
    monkeypatch.setattr(scan_mod.settings, "managed_agent_id", "agent_test")
    monkeypatch.setattr(scan_mod.settings, "managed_environment_id", "env_test")


@pytest.fixture
def patched_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the citation-resolve probe used by the managed driver."""
    # The driver imports retrieve_for_citation lazily inside
    # _resolve_agent_citation, so we patch the source module.
    import swiss_legal_api.engine.retrieval as retrieval_mod
    monkeypatch.setattr(retrieval_mod, "retrieve_for_citation", _stub_chunk)
    # Local verifier path also uses retrieve_for_citation; stub there
    # too in case a downstream code path falls through to it.
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", _stub_chunk)


def _install_fake_run_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reply_json: dict[str, Any],
    provenance: AgentProvenance,
    call_counter: list[int] | None = None,
    captured_brief: list[str] | None = None,
) -> None:
    """Replace agent_runner.run_session AND re-bind the lazy import.

    ``scan._verify_via_managed_session`` does ``from .agent_runner import
    run_session`` inside the function, so we must patch the source
    module — patching scan_mod has no effect on the lazy import.
    """
    from swiss_legal_api.engine import agent_runner

    async def fake_run_session(
        user_message: str,
        *,
        site: str = "engine.scan.batch",
        metadata: dict[str, str] | None = None,
        transport: Any = None,
    ) -> tuple[str, AgentProvenance]:
        if call_counter is not None:
            call_counter.append(1)
        if captured_brief is not None:
            captured_brief.append(user_message)
        return json.dumps(reply_json), provenance

    monkeypatch.setattr(agent_runner, "run_session", fake_run_session)


@pytest.mark.asyncio
async def test_managed_scan_opens_one_session_for_whole_batch(
    force_managed: None,
    patched_resolution: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The managed path must NOT fan out one session per entitlement."""
    catalog = load_catalog()
    profile = _luis()

    # First do a dry-run trigger phase to know which entitlements will
    # be in the batch — we have to seed the agent reply with their IDs.
    triggered_ids: list[str] = []
    for e in catalog:
        r = scan_mod.evaluate_trigger(e.trigger, profile)
        if r.matched and not scan_mod._all_citations_pending(
            e, scan_mod._pending_corpus_articles()
        ):
            triggered_ids.append(e.id)

    assert triggered_ids, "fixture should trigger ≥1 entitlement"

    by_id = {e.id: e for e in catalog}
    reply = {
        "verifications": [
            {
                "entitlement_id": eid,
                "supports": True,
                "confidence": 0.88,
                "reasoning": f"Agent verified {eid}.",
                "best_quote": "Stubbed verbatim quote.",
                "citation": {
                    "sr_number": by_id[eid].source_citations[0].sr_number,
                    "article": by_id[eid].source_citations[0].article,
                    "paragraph": by_id[eid].source_citations[0].paragraph,
                    "language": by_id[eid].source_citations[0].language,
                },
            }
            for eid in triggered_ids
        ]
    }
    provenance = _make_provenance(mcp_calls=len(triggered_ids))
    counter: list[int] = []
    captured: list[str] = []
    _install_fake_run_session(
        monkeypatch,
        reply_json=reply,
        provenance=provenance,
        call_counter=counter,
        captured_brief=captured,
    )

    report = await run_benefit_scan(profile, catalog)

    assert sum(counter) == 1, (
        f"managed scan must open exactly one session, got {sum(counter)}"
    )
    # Brief must list every triggered entitlement_id so the agent
    # actually has the work scoped — no implicit fan-out.
    brief = captured[0]
    for eid in triggered_ids:
        assert eid in brief, f"entitlement {eid} missing from agent brief"

    # Schema-level invariants preserved.
    assert len(report.benefits) == len(triggered_ids)
    for b in report.benefits:
        assert b.citations, f"benefit {b.entitlement_id} has no citations"
        assert b.agent_provenance is not None
        assert b.agent_provenance.call_kind == "sessions.events"
        assert b.agent_provenance.session_id == "sess_managed_scan"


@pytest.mark.asyncio
async def test_managed_scan_suppresses_unresolved_citations(
    force_managed: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An entitlement whose agent-claimed citation does not resolve to
    the corpus must be suppressed with the requires_evidence_review
    reason — never silently promoted into ``benefits``.
    """
    catalog = load_catalog()
    profile = _luis()
    triggered_ids = [
        e.id
        for e in catalog
        if scan_mod.evaluate_trigger(e.trigger, profile).matched
        and not scan_mod._all_citations_pending(
            e, scan_mod._pending_corpus_articles()
        )
    ]
    assert len(triggered_ids) >= 2, "need ≥2 to mix resolved + unresolved"

    by_id = {e.id: e for e in catalog}
    good_id = triggered_ids[0]
    bad_id = triggered_ids[1]

    reply = {
        "verifications": [
            {
                "entitlement_id": good_id,
                "supports": True,
                "confidence": 0.9,
                "reasoning": "good",
                "best_quote": "verbatim",
                "citation": {
                    "sr_number": by_id[good_id].source_citations[0].sr_number,
                    "article": by_id[good_id].source_citations[0].article,
                    "paragraph": None,
                    "language": "de",
                },
            },
            {
                "entitlement_id": bad_id,
                "supports": True,
                "confidence": 0.95,
                "reasoning": "bad — citation does not resolve",
                "best_quote": "verbatim",
                "citation": {
                    "sr_number": "999",  # not in corpus
                    "article": "1",
                    "paragraph": None,
                    "language": "de",
                },
            },
        ]
    }
    # Resolve only the good citation; everything else returns [].
    good_sr = by_id[good_id].source_citations[0].sr_number
    good_art = by_id[good_id].source_citations[0].article

    def selective_resolve(citation: Any, *args: Any, **kwargs: Any) -> Any:
        if citation.sr_number == good_sr and citation.article == good_art:
            return _stub_chunk(citation)
        return []

    import swiss_legal_api.engine.retrieval as retrieval_mod
    monkeypatch.setattr(retrieval_mod, "retrieve_for_citation", selective_resolve)
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", selective_resolve)

    _install_fake_run_session(
        monkeypatch,
        reply_json=reply,
        provenance=_make_provenance(mcp_calls=2),
    )

    report = await run_benefit_scan(profile, catalog)

    benefit_ids = {b.entitlement_id for b in report.benefits}
    assert good_id in benefit_ids
    assert bad_id not in benefit_ids
    # Suppressed counter increments for the unresolved one (and for
    # any other triggered entitlements not in the agent's reply).
    assert report.suppressed_count >= 1


@pytest.mark.asyncio
async def test_managed_scan_no_mcp_tools_suppresses_everything(
    force_managed: None,
    patched_resolution: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hard gate: a session that ran zero MCP tool calls cannot have
    grounded any verdict. Every triggered entitlement must be
    suppressed regardless of what the agent's text said.
    """
    catalog = load_catalog()
    profile = _luis()
    triggered_ids = [
        e.id
        for e in catalog
        if scan_mod.evaluate_trigger(e.trigger, profile).matched
        and not scan_mod._all_citations_pending(
            e, scan_mod._pending_corpus_articles()
        )
    ]
    by_id = {e.id: e for e in catalog}

    reply = {
        "verifications": [
            {
                "entitlement_id": eid,
                "supports": True,
                "confidence": 0.99,
                "reasoning": "trust me",
                "best_quote": "trust me",
                "citation": {
                    "sr_number": by_id[eid].source_citations[0].sr_number,
                    "article": by_id[eid].source_citations[0].article,
                    "paragraph": None,
                    "language": "de",
                },
            }
            for eid in triggered_ids
        ]
    }
    _install_fake_run_session(
        monkeypatch,
        reply_json=reply,
        provenance=_make_provenance(mcp_calls=0, tool_calls=0),
    )

    report = await run_benefit_scan(profile, catalog)
    assert report.benefits == []
    assert report.suppressed_count >= len(triggered_ids)


@pytest.mark.asyncio
async def test_managed_scan_force_local_keeps_per_entitlement_path(
    force_managed: None,
    patched_resolution: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``force_local=True`` (the MCP benefit_scan wrapper's contract)
    must keep using ``_verify_local`` even when use_managed_agents=True.
    The agent driver MUST NOT be invoked.
    """
    sentinel = {"called": False}

    async def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        sentinel["called"] = True
        raise AssertionError("agent driver must not run on force_local path")

    monkeypatch.setattr(scan_mod, "_verify_via_managed_session", boom)

    # _verify_local needs a Claude stub; respx is overkill here — patch
    # _call_claude on the verify module directly.
    fake_prov = AgentProvenance(
        call_kind="messages.create",
        agent_backed=False,
        model="claude-stub",
        latency_ms=1,
    )

    async def fake_call_claude(
        content: str, *, site: str = "x", user_id: str = "anonymous"
    ) -> tuple[str, AgentProvenance]:
        return (
            json.dumps(
                {
                    "supports": True,
                    "confidence": 0.85,
                    "reasoning": "local",
                    "best_quote": "verbatim",
                }
            ),
            fake_prov,
        )

    monkeypatch.setattr(verify_mod, "_call_claude", fake_call_claude)

    report = await run_benefit_scan(_luis(), load_catalog(), force_local=True)
    assert sentinel["called"] is False
    assert len(report.benefits) >= 1
