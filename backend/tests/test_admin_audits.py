import pytest

from swiss_legal_api.audits import agent_backed_summary
from swiss_legal_api.schemas import AgentProvenance, Benefit, BenefitReport


@pytest.fixture
def mock_storage(monkeypatch):
    rep1 = BenefitReport.model_construct(
        user_id="user1",
        generated_at="2026-05-02T10:00:00Z",
        benefits=[
            Benefit.model_construct(
                entitlement_id="test1",
                status="APPROVED",
                agent_provenance=AgentProvenance.model_construct(
                    agent_backed=False,
                    output_tokens=50,
                    call_kind="messages.create",
                    model="claude-3-5-sonnet",
                    latency_ms=100,
                ),
                confidence=0.9,
            ),
            Benefit.model_construct(
                entitlement_id="test2",
                status="APPROVED",
                agent_provenance=AgentProvenance.model_construct(
                    agent_backed=False,
                    output_tokens=50,
                    call_kind="messages.create",
                    model="claude-3-5-sonnet",
                    latency_ms=100,
                ),
                confidence=0.9,
            ),
        ],
        suppressed_count=0,
        profile_hash="123",
    )
    rep2 = BenefitReport.model_construct(
        user_id="user2",
        generated_at="2026-05-02T11:00:00Z",
        benefits=[
            Benefit.model_construct(
                entitlement_id="test3",
                status="APPROVED",
                agent_provenance=AgentProvenance.model_construct(
                    agent_backed=True,
                    output_tokens=50,
                    call_kind="sessions.events",
                    model="claude-3-5-sonnet",
                    latency_ms=100,
                ),
                confidence=0.9,
            ),
            Benefit.model_construct(
                entitlement_id="test4",
                status="APPROVED",
                agent_provenance=AgentProvenance.model_construct(
                    agent_backed=True,
                    output_tokens=50,
                    call_kind="sessions.events",
                    model="claude-3-5-sonnet",
                    latency_ms=100,
                ),
                confidence=0.9,
            ),
            Benefit.model_construct(
                entitlement_id="test5",
                status="APPROVED",
                agent_provenance=AgentProvenance.model_construct(
                    agent_backed=True,
                    output_tokens=50,
                    call_kind="sessions.events",
                    model="claude-3-5-sonnet",
                    latency_ms=100,
                ),
                confidence=0.9,
            ),
            Benefit.model_construct(
                entitlement_id="test6",
                status="APPROVED",
                agent_provenance=AgentProvenance.model_construct(
                    agent_backed=False,
                    output_tokens=50,
                    call_kind="messages.create",
                    model="claude-3-5-sonnet",
                    latency_ms=100,
                ),
                confidence=0.9,
            ),
        ],
        suppressed_count=0,
        profile_hash="123",
    )
    monkeypatch.setattr(
        "swiss_legal_api.audits.storage.iter_all_scans", lambda *a, **kw: [rep1, rep2]
    )


def test_admin_audit_agent_backed_percentage(mock_storage):
    data = agent_backed_summary()
    assert data["total_benefits"] == 6
    assert data["agent_backed"] == 3
    assert data["unverified_by_agent"] == 3
    assert data["agent_backed_pct"] == 0.5


def test_admin_audit_agent_backed_since(mock_storage):
    data = agent_backed_summary(since="2026-05-02T10:30:00Z")
    assert data["total_benefits"] == 4
    assert data["agent_backed"] == 3
    assert data["unverified_by_agent"] == 1
    assert data["agent_backed_pct"] == 0.75
