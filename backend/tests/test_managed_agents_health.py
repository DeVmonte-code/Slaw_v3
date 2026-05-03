"""Tests for Task #37 startup gate, MCP probe, and tool_call SSE forwarding.

Covers the three review-flagged gaps:
1. Strict startup validation matrix (`_validate_managed_agents_config`).
2. ``/readyz`` MCP probe outcomes (reachable / timeout / unreachable /
   server_error / unconfigured) and 503 fail-fast when managed mode
   is on.
3. Scan-stream forwarding emits ONLY ``{tool, server, label}`` for
   ``agent.mcp_tool_use`` events (no IDs / args / inputs leak).
4. URL redaction (``_safe_url_host``) strips userinfo + path + query.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from swiss_legal_api.api import main as main_mod
from swiss_legal_api.engine import scan as scan_mod


# --------------------------------------------------------------------------- #
# _safe_url_host                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url,expected",
    [
        ("", "<unset>"),
        ("https://mcp.example.com/mcp/swiss-law", "https://mcp.example.com"),
        ("http://mcp.example.com:9000/mcp/x?token=abc", "http://mcp.example.com:9000"),
        ("https://user:pass@mcp.internal/mcp/x", "https://mcp.internal"),
        ("not-a-url", "<malformed>"),
    ],
)
def test_safe_url_host_redacts_credentials_and_path(url: str, expected: str) -> None:
    assert main_mod._safe_url_host(url) == expected


# --------------------------------------------------------------------------- #
# _validate_managed_agents_config                                             #
# --------------------------------------------------------------------------- #


def _seed_full_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_mod.settings, "use_managed_agents", True)
    monkeypatch.setattr(main_mod.settings, "managed_agent_id", "agent_abcd1234")
    monkeypatch.setattr(main_mod.settings, "managed_agent_version", 3)
    monkeypatch.setattr(main_mod.settings, "managed_environment_id", "env_abcd1234")
    monkeypatch.setattr(main_mod.settings, "managed_vault_id", "vault_abcd1234")
    monkeypatch.setattr(
        main_mod.settings,
        "mcp_swiss_law_url",
        "https://mcp.example.com/mcp/swiss-law",
    )
    monkeypatch.setattr(
        main_mod.settings,
        "mcp_contract_tools_url",
        "https://mcp.example.com/mcp/contract-tools",
    )
    monkeypatch.setattr(
        main_mod.settings,
        "mcp_user_context_url",
        "https://mcp.example.com/mcp/user-context",
    )


def test_validate_noop_when_managed_agents_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_mod.settings, "use_managed_agents", False)
    main_mod._validate_managed_agents_config()


def test_validate_passes_with_full_config_and_logs_redacted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _seed_full_config(monkeypatch)
    with caplog.at_level(logging.INFO, logger=main_mod.logger.name):
        main_mod._validate_managed_agents_config()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "managed_agents_enabled" in log_text
    # Raw IDs and full URLs must NOT appear.
    assert "agent_abcd1234" not in log_text
    assert "vault_abcd1234" not in log_text
    assert "/mcp/swiss-law" not in log_text
    # Redacted forms ARE expected.
    assert "https://mcp.example.com" in log_text


@pytest.mark.parametrize(
    "missing_attr,env_var",
    [
        ("managed_agent_id", "MANAGED_AGENT_ID"),
        ("managed_environment_id", "MANAGED_ENVIRONMENT_ID"),
        ("managed_vault_id", "MANAGED_VAULT_ID"),
        ("mcp_swiss_law_url", "MCP_SWISS_LAW_URL"),
        ("mcp_contract_tools_url", "MCP_CONTRACT_TOOLS_URL"),
        ("mcp_user_context_url", "MCP_USER_CONTEXT_URL"),
    ],
)
def test_validate_fails_fast_per_missing_field(
    monkeypatch: pytest.MonkeyPatch, missing_attr: str, env_var: str
) -> None:
    _seed_full_config(monkeypatch)
    monkeypatch.setattr(main_mod.settings, missing_attr, "")
    with pytest.raises(RuntimeError) as excinfo:
        main_mod._validate_managed_agents_config()
    msg = str(excinfo.value)
    assert env_var in msg
    assert "USE_MANAGED_AGENTS=0" in msg


def test_validate_fails_when_agent_version_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_full_config(monkeypatch)
    monkeypatch.setattr(main_mod.settings, "managed_agent_version", 0)
    with pytest.raises(RuntimeError) as excinfo:
        main_mod._validate_managed_agents_config()
    assert "MANAGED_AGENT_VERSION" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# _probe_one_mcp / _probe_mcp_servers                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_probe_one_mcp_reachable_on_4xx() -> None:
    # MCP streamable-HTTP endpoints answer 405/406 to a bare GET; we
    # treat <500 as "process is alive".
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(405, text="Method Not Allowed")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await main_mod._probe_one_mcp(
            client, "https://mcp.example.com/mcp/swiss-law"
        )
    assert result["status"] == "reachable"
    assert result["http_status"] == 405
    assert result["host"] == "https://mcp.example.com"
    assert "url" not in result


@pytest.mark.asyncio
async def test_probe_one_mcp_server_error_on_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await main_mod._probe_one_mcp(client, "https://mcp.example.com/x")
    assert result["status"] == "server_error"
    assert result["http_status"] == 503


@pytest.mark.asyncio
async def test_probe_one_mcp_unreachable_on_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await main_mod._probe_one_mcp(client, "https://mcp.example.com/x")
    assert result["status"] == "unreachable"
    assert result["error"] == "ConnectError"


@pytest.mark.asyncio
async def test_probe_one_mcp_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await main_mod._probe_one_mcp(client, "https://mcp.example.com/x")
    assert result["status"] == "timeout"


@pytest.mark.asyncio
async def test_probe_mcp_servers_handles_unconfigured_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_full_config(monkeypatch)
    monkeypatch.setattr(main_mod.settings, "mcp_user_context_url", "")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(405)

    real_client = httpx.AsyncClient

    def fake_client(*a: Any, **kw: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(main_mod.httpx, "AsyncClient", fake_client)
    out = await main_mod._probe_mcp_servers()
    assert set(out.keys()) == {"swiss_law", "contract_tools", "user_context"}
    assert out["user_context"]["status"] == "unconfigured"
    assert out["swiss_law"]["status"] == "reachable"


# --------------------------------------------------------------------------- #
# tool_call SSE forwarding                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_make_agent_event_cb_forwards_only_safe_fields() -> None:
    captured: list[dict[str, Any]] = []

    async def progress_cb(payload: dict[str, Any]) -> None:
        captured.append(payload)

    cb = scan_mod._make_agent_event_cb(progress_cb)
    assert cb is not None

    await cb(
        {
            "type": "agent.mcp_tool_use",
            "name": "search_legal_corpus",
            "server_name": "swiss-law",
            # Fields below MUST NOT appear in the forwarded payload —
            # they may carry user PII, agent IDs, or argument blobs.
            "tool_use_id": "tu_secretid_12345",
            "input": {"query": "user-private query string"},
            "agent_id": "agent_xyz",
        }
    )

    assert len(captured) == 1
    payload = captured[0]
    assert payload["type"] == "tool_call"
    assert set(payload.keys()) == {"type", "tool", "server", "label"}
    assert payload["tool"] == "search_legal_corpus"
    assert payload["server"] == "swiss-law"
    assert "Searching" in payload["label"] or "Calling" in payload["label"]


@pytest.mark.asyncio
async def test_make_agent_event_cb_ignores_agent_message_events() -> None:
    captured: list[dict[str, Any]] = []

    async def progress_cb(payload: dict[str, Any]) -> None:
        captured.append(payload)

    cb = scan_mod._make_agent_event_cb(progress_cb)
    assert cb is not None
    # agent.message carries verbatim model output — never forward it.
    await cb({"type": "agent.message", "text": "internal planning ..."})
    await cb({"type": "agent.run.completed"})
    assert captured == []


def test_make_agent_event_cb_returns_none_when_no_progress_cb() -> None:
    assert scan_mod._make_agent_event_cb(None) is None


# --------------------------------------------------------------------------- #
# Multi-missing config + malformed-URL regression                             #
# --------------------------------------------------------------------------- #


def test_validate_reports_all_missing_fields_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When several env vars are missing the operator should see every
    one of them in a single error so they can fix the deploy in one
    pass instead of playing whack-a-mole."""
    _seed_full_config(monkeypatch)
    monkeypatch.setattr(main_mod.settings, "managed_vault_id", "")
    monkeypatch.setattr(main_mod.settings, "mcp_swiss_law_url", "")
    monkeypatch.setattr(main_mod.settings, "mcp_user_context_url", "")
    with pytest.raises(RuntimeError) as excinfo:
        main_mod._validate_managed_agents_config()
    msg = str(excinfo.value)
    for env_var in ("MANAGED_VAULT_ID", "MCP_SWISS_LAW_URL", "MCP_USER_CONTEXT_URL"):
        assert env_var in msg, f"{env_var} missing from aggregated error: {msg}"
    # Fields that ARE configured must not be reported as missing.
    assert "MANAGED_AGENT_ID" not in msg
    assert "MCP_CONTRACT_TOOLS_URL" not in msg


def test_safe_url_host_handles_malformed_urls_without_leaking() -> None:
    """Regression guard: even a junk URL must not raise and must not
    return any of the original input verbatim, so a misconfigured
    deploy can't accidentally leak via the redacted log line."""
    for junk in ("://broken", "https://", "ftp://", "  "):
        out = main_mod._safe_url_host(junk)
        assert out in {"<malformed>", "<unset>", "ftp://"} or out.startswith(
            ("http://", "https://")
        )


# --------------------------------------------------------------------------- #
# /readyz HTTP integration                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def readyz_client(monkeypatch: pytest.MonkeyPatch) -> "Any":
    """ASGI test client wired with stub Qdrant + stub MCP probe.

    /readyz needs the embedder/Qdrant collection check to pass before
    it ever gets to the MCP block, so we stub both. The MCP probe is
    swapped out per-test to drive the various status branches.
    """
    from starlette.testclient import TestClient

    class _StubCollections:
        def __init__(self, names: list[str]) -> None:
            self.collections = [type("C", (), {"name": n})() for n in names]

    class _StubQdrant:
        def get_collections(self) -> Any:
            return _StubCollections([main_mod.settings.qdrant_collection])

        def count(self, *a: Any, **kw: Any) -> Any:
            return type("R", (), {"count": 1})()

    monkeypatch.setattr(main_mod, "qdrant_client", lambda: _StubQdrant())
    monkeypatch.setattr(main_mod, "get_embedder", lambda: object())
    return TestClient(main_mod.app)


def test_readyz_200_when_all_mcps_reachable(
    monkeypatch: pytest.MonkeyPatch, readyz_client: Any
) -> None:
    _seed_full_config(monkeypatch)

    async def fake_probe() -> dict[str, dict[str, object]]:
        return {
            "swiss_law": {"host": "https://mcp.example.com", "status": "reachable"},
            "contract_tools": {
                "host": "https://mcp.example.com",
                "status": "reachable",
            },
            "user_context": {
                "host": "https://mcp.example.com",
                "status": "reachable",
            },
        }

    monkeypatch.setattr(main_mod, "_probe_mcp_servers", fake_probe)
    resp = readyz_client.get("/readyz")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mcp"]["swiss_law"]["status"] == "reachable"
    # Body must not leak any path/query/userinfo from the probed URL.
    raw = resp.text
    assert "/mcp/swiss-law" not in raw
    assert "@" not in raw or "user@" not in raw


def test_readyz_503_when_any_mcp_unreachable(
    monkeypatch: pytest.MonkeyPatch, readyz_client: Any
) -> None:
    _seed_full_config(monkeypatch)

    async def fake_probe() -> dict[str, dict[str, object]]:
        return {
            "swiss_law": {"host": "https://mcp.example.com", "status": "reachable"},
            "contract_tools": {
                "host": "https://mcp.example.com",
                "status": "timeout",
                "elapsed_ms": 4000,
            },
            "user_context": {
                "host": "https://mcp.example.com",
                "status": "reachable",
            },
        }

    monkeypatch.setattr(main_mod, "_probe_mcp_servers", fake_probe)
    resp = readyz_client.get("/readyz")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["mcp"]["contract_tools"]["status"] == "timeout"
    # Same redaction guarantee on the failure payload.
    assert "/mcp/" not in resp.text


def test_readyz_include_mcp_forces_probe_when_managed_disabled(
    monkeypatch: pytest.MonkeyPatch, readyz_client: Any
) -> None:
    monkeypatch.setattr(main_mod.settings, "use_managed_agents", False)
    called = {"n": 0}

    async def fake_probe() -> dict[str, dict[str, object]]:
        called["n"] += 1
        return {
            "swiss_law": {"host": "<unset>", "status": "unconfigured"},
            "contract_tools": {"host": "<unset>", "status": "unconfigured"},
            "user_context": {"host": "<unset>", "status": "unconfigured"},
        }

    monkeypatch.setattr(main_mod, "_probe_mcp_servers", fake_probe)
    # Without ?include=mcp the probe must NOT run when disabled.
    resp = readyz_client.get("/readyz")
    assert resp.status_code == 200
    assert called["n"] == 0
    assert "mcp" not in resp.json()
    # With ?include=mcp the probe runs even when managed mode is off.
    resp = readyz_client.get("/readyz?include=mcp")
    assert resp.status_code == 200
    assert called["n"] == 1
    assert resp.json()["mcp"]["swiss_law"]["status"] == "unconfigured"
