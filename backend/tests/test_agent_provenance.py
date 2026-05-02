"""Regression tests for the Task #25 agent-backed audit contract.

Two non-negotiable invariants:

(i)  Every persisted ``Benefit`` MUST carry an ``agent_provenance`` —
     a future refactor of the verifier or scan orchestrator cannot
     silently drop the audit field. Both the success path and the
     bad-JSON short-circuit path are exercised.

(ii) The audit aggregation (CLI and ``/admin/audits/agent-backed``
     endpoint) reads what the verifier wrote and answers the
     baseline question: "are we agent-backed yet?". For Task #25
     the answer is no (every call site still uses
     ``messages.create``); for Task #26 the same query will flip to
     ``agent_backed_pct > 0``.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from swiss_legal_api import storage
from swiss_legal_api.api.main import app
from swiss_legal_api.audits import agent_backed_summary
from swiss_legal_api.engine import verify as verify_mod
from swiss_legal_api.engine.retrieval import RetrievedChunk
from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.engine.verify import VerifyResult, verify_entitlement
from swiss_legal_api.schemas import (
    AgentProvenance,
    ContextProfile,
    Entitlement,
)


@pytest.fixture(autouse=True)
def _isolated_storage() -> None:
    storage.set_db_path(":memory:")
    yield
    storage.reset_for_tests()


def _profile() -> ContextProfile:
    return ContextProfile.model_validate(
        {
            "canton": "ZH",
            "employment_status": "employee_full_time",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "80_120k",
        }
    )


def _entitlement() -> Entitlement:
    return Entitlement.model_validate(
        {
            "id": "test_ent_prov",
            "title": {"de": "Test", "en": "Test entitlement"},
            "category": "tax_deduction",
            "jurisdiction": "CH",
            "source_citations": [
                {
                    "sr_number": "642.11",
                    "article": "33",
                    "language": "de",
                    "quote_under_15_words": "Test quote in German.",
                }
            ],
            "trigger": {"all": []},
            "estimated_value_chf": {"min": 0, "max": 100, "per": "year"},
            "required_action": "tax_declaration_field",
            "confidence_floor": 0.0,
        }
    )


def test_verify_result_default_provenance_is_messages_create() -> None:
    """The dataclass default keeps the contract: every VerifyResult has
    provenance, even when constructed without one (short-circuit paths)."""
    cit = _entitlement().source_citations[0]
    r = VerifyResult(supports=False, confidence=0.0, reasoning="x", best_citation=cit)
    assert r.agent_provenance is not None
    assert r.agent_provenance.call_kind == "messages.create"
    assert r.agent_provenance.agent_backed is False


@pytest.mark.asyncio
async def test_verify_entitlement_attaches_provenance(monkeypatch) -> None:
    """Successful verification surfaces the same provenance the call site
    emitted — call_kind, model, latency_ms all flow through."""
    chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.91,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", lambda *a, **k: [chunk])

    async def _fake_call_claude(_user: str) -> tuple[str, AgentProvenance]:
        return (
            json.dumps(
                {
                    "supports": True,
                    "confidence": 0.9,
                    "reasoning": "ok",
                    "best_quote": "Quote within fifteen words.",
                }
            ),
            AgentProvenance(
                call_kind="messages.create",
                agent_backed=False,
                model="claude-fake",
                latency_ms=42,
                input_tokens=10,
                output_tokens=5,
            ),
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    result = await verify_entitlement(_entitlement(), _profile(), [])

    assert result.agent_provenance.call_kind == "messages.create"
    assert result.agent_provenance.agent_backed is False
    assert result.agent_provenance.model == "claude-fake"
    assert result.agent_provenance.latency_ms == 42


@pytest.mark.asyncio
async def test_bad_json_path_still_carries_provenance(monkeypatch) -> None:
    """The LLM-returned-garbage short-circuit must NOT drop provenance —
    auditors need to see that we made the call and got useless output,
    not that the call never happened."""
    chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.91,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", lambda *a, **k: [chunk])

    async def _fake_call_claude(_user: str) -> tuple[str, AgentProvenance]:
        return "this is not json at all", AgentProvenance(
            call_kind="messages.create",
            agent_backed=False,
            model="claude-fake",
            latency_ms=7,
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    result = await verify_entitlement(_entitlement(), _profile(), [])

    assert result.supports is False
    assert result.agent_provenance.model == "claude-fake"
    assert result.agent_provenance.latency_ms == 7


@pytest.mark.asyncio
async def test_persisted_benefit_round_trips_provenance(monkeypatch) -> None:
    """End-to-end: scan → persist → re-load. The persisted Benefit MUST
    deserialize with agent_provenance populated. This is the regression
    that fails when a future refactor drops the audit field."""
    chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.91,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", lambda *a, **k: [chunk])

    async def _fake_call_claude(_user: str) -> tuple[str, AgentProvenance]:
        return (
            json.dumps(
                {
                    "supports": True,
                    "confidence": 0.9,
                    "reasoning": "ok",
                    "best_quote": "Quote within fifteen words.",
                }
            ),
            AgentProvenance(
                call_kind="messages.create",
                agent_backed=False,
                model="claude-fake",
                latency_ms=11,
            ),
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    report = await run_benefit_scan(_profile(), [_entitlement()])
    assert len(report.benefits) == 1
    assert report.benefits[0].agent_provenance is not None
    assert report.benefits[0].agent_provenance.agent_backed is False

    storage.upsert_user("u1", _profile(), notify_enabled=True)
    storage.insert_scan("u1", report)
    rehydrated = storage.latest_scan("u1")
    assert rehydrated is not None
    assert rehydrated.benefits[0].agent_provenance is not None
    assert rehydrated.benefits[0].agent_provenance.call_kind == "messages.create"


@pytest.mark.asyncio
async def test_audit_summary_baseline_is_zero_agent_backed(monkeypatch) -> None:
    """Baseline assertion for Task #25: with the current call sites,
    the audit endpoint and the CLI must report agent_backed_pct=0.0."""
    chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.91,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", lambda *a, **k: [chunk])

    async def _fake_call_claude(_u: str) -> tuple[str, AgentProvenance]:
        return (
            json.dumps(
                {
                    "supports": True,
                    "confidence": 0.9,
                    "reasoning": "ok",
                    "best_quote": "Quote within fifteen words.",
                }
            ),
            AgentProvenance(
                call_kind="messages.create",
                agent_backed=False,
                model="claude-fake",
                latency_ms=3,
            ),
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    report = await run_benefit_scan(_profile(), [_entitlement()])
    storage.upsert_user("u1", _profile(), notify_enabled=True)
    storage.insert_scan("u1", report)

    summary = agent_backed_summary()
    assert summary["total_benefits"] == 1
    assert summary["agent_backed"] == 0
    assert summary["unverified_by_agent"] == 1
    assert summary["agent_backed_pct"] == 0.0
    assert summary["by_call_kind"] == {"messages.create": 1}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/admin/audits/agent-backed")
        assert r.status_code == 200
        body = r.json()
        assert body["agent_backed_pct"] == 0.0
        assert body["total_benefits"] == 1


@pytest.mark.asyncio
async def test_legacy_benefit_without_provenance_counts_as_unknown() -> None:
    """A Benefit serialised before Task #25 lands has no
    agent_provenance — the audit must surface it under ``unknown``
    rather than blowing up or silently counting it as agent-backed."""
    legacy_report = {
        "generated_at": "2026-04-01T00:00:00Z",
        "profile_hash": "deadbeefdeadbeef",
        "benefits": [
            {
                "entitlement_id": "legacy",
                "title": "Legacy benefit",
                "category": "tax_deduction",
                "estimated_value_chf": {"min": 0, "max": 100, "per": "year"},
                "confidence": 0.9,
                "citations": [
                    {
                        "sr_number": "642.11",
                        "article": "33",
                        "language": "de",
                        "quote_under_15_words": "Quote.",
                    }
                ],
                "evidence": [],
                "required_action": "tax_declaration_field",
                "llm_reasoning": "ok",
            }
        ],
        "suppressed_count": 0,
    }
    from swiss_legal_api.schemas import BenefitReport

    report = BenefitReport.model_validate(legacy_report)
    assert report.benefits[0].agent_provenance is None
    storage.upsert_user("u1", _profile(), notify_enabled=True)
    storage.insert_scan("u1", report)

    summary = agent_backed_summary()
    assert summary["unknown_provenance"] == 1
    assert summary["agent_backed"] == 0


@pytest.mark.asyncio
async def test_audit_counts_every_persisted_scan_not_just_latest(monkeypatch) -> None:
    """A user with N persisted scans must contribute N reports' worth of
    benefits to the aggregate. The audit cannot silently restrict to
    ``latest_scan`` per user — that would distort the headline
    ``agent_backed_pct`` toward heavy users.
    """
    chunk = RetrievedChunk(
        text="Originaler deutscher Gesetzestext.",
        score=0.91,
        language="de",
        effective_date=date(1995, 1, 1),
    )
    monkeypatch.setattr(verify_mod, "retrieve_for_citation", lambda *a, **k: [chunk])

    async def _fake_call_claude(_u: str) -> tuple[str, AgentProvenance]:
        return (
            json.dumps(
                {
                    "supports": True,
                    "confidence": 0.9,
                    "reasoning": "ok",
                    "best_quote": "Quote within fifteen words.",
                }
            ),
            AgentProvenance(
                call_kind="messages.create",
                agent_backed=False,
                model="claude-fake",
                latency_ms=3,
            ),
        )

    monkeypatch.setattr(verify_mod, "_call_claude", _fake_call_claude)

    storage.upsert_user("u1", _profile(), notify_enabled=True)

    # Three scans with distinct generated_at so the (user_id, scan_at)
    # primary key keeps all three rows. Each scan has one benefit, so
    # the aggregate must report total_benefits=3.
    for ts in ("2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z", "2026-04-03T00:00:00Z"):
        report = await run_benefit_scan(_profile(), [_entitlement()])
        report = report.model_copy(update={"generated_at": ts})
        storage.insert_scan("u1", report)

    summary = agent_backed_summary()
    assert summary["total_benefits"] == 3
    assert summary["unverified_by_agent"] == 3
    assert summary["agent_backed"] == 0


@pytest.mark.asyncio
async def test_admin_endpoint_blocks_when_unset_in_production(monkeypatch) -> None:
    """In production with no token configured the endpoint must 403 —
    a misconfigured deploy must not silently expose the audit data."""
    from swiss_legal_api.config import settings

    monkeypatch.setattr(settings, "admin_audit_token", "")
    monkeypatch.setattr(type(settings), "is_production", lambda self: True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/admin/audits/agent-backed")
        assert r.status_code == 403


def test_managed_agents_provenance_invariant() -> None:
    """Hand-off guardrail for Task #26.

    When the call sites flip to ``sessions.events``, ``agent_backed``
    must remain a *derived* signal — true iff the session emitted ≥1
    tool/MCP-tool event. Building an inconsistent provenance (e.g.
    ``call_kind='sessions.events'`` with zero tool use but
    ``agent_backed=True``) should be a code smell the migration test
    suite catches before it ships. This test pins the rule by
    exercising both halves.
    """
    consistent_messages = AgentProvenance(
        call_kind="messages.create",
        agent_backed=False,
        model="m",
        latency_ms=0,
    )
    assert _is_consistent(consistent_messages)

    consistent_session_with_tool = AgentProvenance(
        call_kind="sessions.events",
        agent_backed=True,
        model="m",
        latency_ms=0,
        tool_use_count=1,
    )
    assert _is_consistent(consistent_session_with_tool)

    inconsistent = AgentProvenance(
        call_kind="messages.create",
        agent_backed=True,  # impossible: no managed-agent session ran
        model="m",
        latency_ms=0,
    )
    assert not _is_consistent(inconsistent)

    inconsistent_no_tools = AgentProvenance(
        call_kind="sessions.events",
        agent_backed=True,
        model="m",
        latency_ms=0,
        tool_use_count=0,
        mcp_tool_use_count=0,
    )
    assert not _is_consistent(inconsistent_no_tools)


def _is_consistent(p: AgentProvenance) -> bool:
    if p.call_kind == "messages.create":
        return p.agent_backed is False
    return p.agent_backed == ((p.tool_use_count + p.mcp_tool_use_count) > 0)


@pytest.mark.asyncio
async def test_admin_endpoint_token_gate(monkeypatch) -> None:
    """When ADMIN_AUDIT_TOKEN is set, the endpoint requires the header."""
    from swiss_legal_api.config import settings

    monkeypatch.setattr(settings, "admin_audit_token", "shh-secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/admin/audits/agent-backed")
        assert r.status_code == 403
        r = await c.get(
            "/admin/audits/agent-backed",
            headers={"X-Admin-Token": "wrong"},
        )
        assert r.status_code == 403
        r = await c.get(
            "/admin/audits/agent-backed",
            headers={"X-Admin-Token": "shh-secret"},
        )
        assert r.status_code == 200
