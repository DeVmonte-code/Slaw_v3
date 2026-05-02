"""Unit tests for :mod:`swiss_legal_api.engine.agent_runner` (Task #26).

We never hit the real Anthropic Managed Agents API — instead we use
``httpx.MockTransport`` to replay a canned SSE stream. The assertions
focus on the audit contract:

- A session that emits ≥1 ``agent.tool_use`` (or ``agent.mcp_tool_use``)
  produces ``AgentProvenance(call_kind="sessions.events", agent_backed=True)``.
- A session with zero tool uses produces ``agent_backed=False`` —
  the schema's model_validator would otherwise reject the record, so
  this is the contract we ship.
- A ``session.status_terminated`` event raises ``ManagedAgentsError``
  rather than returning silent zeros.
- Missing bootstrap IDs raise ``ManagedAgentsConfigError``.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest

from swiss_legal_api.config import settings
from swiss_legal_api.engine import agent_runner


def _sse(events: list[dict[str, object]]) -> bytes:
    """Render a list of event dicts as an SSE response body."""
    return ("\n".join(f"data: {json.dumps(e)}" for e in events) + "\n").encode()


def _make_transport(stream_events: list[dict[str, object]]) -> httpx.MockTransport:
    """Mock /v1/sessions, /events, and /stream — the three calls the runner makes."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sessions" and request.method == "POST":
            return httpx.Response(200, json={"id": "sess_test_123"})
        if request.url.path.endswith("/events") and request.method == "POST":
            return httpx.Response(200, json={"ok": True})
        if request.url.path.endswith("/stream") and request.method == "GET":
            return httpx.Response(
                200,
                content=_sse(stream_events),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404, json={"error": f"unmocked {request.url.path}"})

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _configure_managed_agents() -> Iterator[None]:
    """Populate the bootstrap IDs so the runner's _require_config passes."""
    prev = (
        settings.managed_agent_id,
        settings.managed_agent_version,
        settings.managed_environment_id,
        settings.managed_vault_id,
    )
    settings.managed_agent_id = "agent_test"
    settings.managed_agent_version = 1
    settings.managed_environment_id = "env_test"
    settings.managed_vault_id = "vault_test"
    yield
    (
        settings.managed_agent_id,
        settings.managed_agent_version,
        settings.managed_environment_id,
        settings.managed_vault_id,
    ) = prev


async def test_tool_use_flips_agent_backed_true() -> None:
    transport = _make_transport(
        [
            {"type": "agent.tool_use", "name": "qdrant_search"},
            {
                "type": "agent.mcp_tool_use",
                "name": "fetch_article_by_sr",
                "server_name": "swiss-law-retrieval-mcp",
            },
            {
                "type": "agent.message",
                "content": [
                    {
                        "type": "text",
                        "text": '{"supports": true, "confidence": 0.9, '
                        '"reasoning": "ok", "best_quote": "quote"}',
                    }
                ],
            },
            {"type": "session.status_idle"},
        ]
    )
    text, prov = await agent_runner.run_session(
        "verify entitlement X", site="engine.verify:test", transport=transport
    )
    assert "supports" in text
    assert prov.call_kind == "sessions.events"
    assert prov.agent_backed is True
    assert prov.tool_use_count == 1
    assert prov.mcp_tool_use_count == 1
    assert prov.mcp_servers_invoked == ["swiss-law-retrieval-mcp"]
    assert prov.session_id == "sess_test_123"
    assert prov.agent_id == "agent_test"
    assert prov.environment_id == "env_test"


async def test_zero_tool_use_records_agent_backed_false() -> None:
    transport = _make_transport(
        [
            {
                "type": "agent.message",
                "content": [{"type": "text", "text": "no tools"}],
            },
            {"type": "session.status_idle"},
        ]
    )
    text, prov = await agent_runner.run_session(
        "trivial question", site="api.chat:no_benefit", transport=transport
    )
    assert text == "no tools"
    assert prov.call_kind == "sessions.events"
    # Schema's model_validator enforces this — agent_backed is derived,
    # not free-form. A sessions.events call with zero tool uses is NOT
    # agent-backed; that's the whole point of the audit.
    assert prov.agent_backed is False
    assert prov.tool_use_count == 0
    assert prov.mcp_tool_use_count == 0


async def test_terminated_session_raises_managed_agents_error() -> None:
    transport = _make_transport(
        [
            {
                "type": "session.error",
                "error": {"message": "fatal", "retry_status": "no_retry"},
            },
            {"type": "session.status_terminated"},
        ]
    )
    with pytest.raises(agent_runner.ManagedAgentsError):
        await agent_runner.run_session(
            "trigger termination", site="engine.verify:fail", transport=transport
        )


async def test_retryable_session_error_raises_retryable_exception() -> None:
    """``session.error`` with ``retry_status='retryable'`` must surface
    as :class:`RetryableManagedAgentsError` so the tenacity filter at
    the call site retries it (same backoff as a transport blip)
    instead of failing fatally on the first attempt.
    """
    transport = _make_transport(
        [
            {
                "type": "session.error",
                "error": {"message": "transient", "retry_status": "retryable"},
            },
            {"type": "session.status_idle"},
        ]
    )
    with pytest.raises(agent_runner.RetryableManagedAgentsError):
        await agent_runner.run_session(
            "transient", site="engine.verify:retry", transport=transport
        )


async def test_managed_verify_refuses_when_no_mcp_tool_invoked(
    monkeypatch,
) -> None:
    """Hard gate: the architectural inversion of Task #26 only holds
    if every managed verdict is grounded in an MCP tool call.

    When the agent emits ``session.status_idle`` with zero
    ``agent.mcp_tool_use`` events, ``_verify_via_managed_agent`` must
    refuse with ``supports=False`` rather than parrot the agent's
    ungrounded answer.
    """
    from swiss_legal_api.catalog import load_catalog
    from swiss_legal_api.engine import verify as verify_mod
    from swiss_legal_api.schemas import ContextProfile

    monkeypatch.setattr(settings, "use_managed_agents", True)
    monkeypatch.setattr(settings, "managed_agent_id", "agent_1")
    monkeypatch.setattr(settings, "managed_environment_id", "env_1")
    monkeypatch.setattr(settings, "mcp_swiss_law_url", "https://x")
    monkeypatch.setattr(settings, "mcp_contract_tools_url", "https://x")
    monkeypatch.setattr(settings, "mcp_user_context_url", "https://x")

    transport = _make_transport(
        [
            # Agent answers without ever calling an MCP tool.
            {
                "type": "agent.message",
                "content": [
                    {
                        "type": "text",
                        "text": '{"supports": true, "confidence": 0.9, '
                        '"reasoning": "i just know", "best_quote": "trust me"}',
                    }
                ],
            },
            {"type": "session.status_idle"},
        ]
    )

    async def fake_run_session(
        user_message: str, *, site: str = "engine.verify", transport=None
    ):
        return await agent_runner.run_session(
            user_message, site=site, transport=transport_real
        )

    transport_real = transport
    monkeypatch.setattr(
        verify_mod,
        "_call_claude",
        lambda content, *, site="engine.verify": agent_runner.run_session(
            content, site=site, transport=transport_real
        ),
    )

    ent = load_catalog()[0]
    profile = ContextProfile(
        canton="ZH",
        employment_status="employee_full_time",
        housing_status="tenant",
        household_size=1,
        children_count=0,
        marital_status="single",
        income_band_chf="50_80k",
    )
    result = await verify_mod._verify_via_managed_agent(ent, profile, [])
    assert result.supports is False
    assert "MCP tool" in result.reasoning


async def test_stream_opens_before_user_message_is_sent() -> None:
    """Architect-flagged race: POST /events MUST NOT precede GET /stream.

    The runner uses an asyncio.Event signalled inside ``_stream_events``
    once the streaming GET response is open, then ``await``s it before
    POSTing the user message. We assert the ordering by recording the
    request sequence in the mock transport.
    """
    order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sessions" and request.method == "POST":
            order.append("create")
            return httpx.Response(200, json={"id": "sess_race"})
        if request.url.path.endswith("/stream"):
            order.append("stream")
            return httpx.Response(
                200,
                content=_sse(
                    [
                        {
                            "type": "agent.message",
                            "content": [{"type": "text", "text": "ok"}],
                        },
                        {"type": "session.status_idle"},
                    ]
                ),
                headers={"content-type": "text/event-stream"},
            )
        if request.url.path.endswith("/events"):
            order.append("events")
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    await agent_runner.run_session(
        "race check", site="engine.verify:race", transport=transport
    )
    # The ready barrier guarantees stream is opened before events POST.
    assert order == ["create", "stream", "events"], order


async def test_missing_config_raises_config_error() -> None:
    settings.managed_agent_id = ""
    with pytest.raises(agent_runner.ManagedAgentsConfigError):
        await agent_runner.run_session(
            "anything", site="engine.verify:noconf", transport=_make_transport([])
        )
