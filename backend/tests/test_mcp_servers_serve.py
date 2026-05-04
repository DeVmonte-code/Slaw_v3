"""Smoke tests for the deployed MCP servers (Task #31).

Confirms that:

1. Each ``McpServerSpec`` produces a working ``FastMCP`` instance via
   :func:`mcp_servers.build_fastmcp` (so the Python wrappers are
   actually callable through the MCP protocol layer, not just as
   in-process functions — the SSOT test in
   ``test_mcp_single_source_of_truth.py`` already covers identity).
2. The FastAPI app mounts all three servers at their expected
   prefixes so a ``MCP_BASE_URL=https://<host>`` derivation produces
   the URLs the agent will actually hit.
3. ``Settings.mcp_base_url`` derives the per-server URLs.

These tests stay free of network IO and Anthropic credentials so they
run on every commit, not just deploy-day smoke runs.
"""

from __future__ import annotations

import pytest

from swiss_legal_api.api.main import _MCP_MOUNTS, app
from swiss_legal_api.config import Settings
from swiss_legal_api.mcp_servers import build_fastmcp, contract_tools, swiss_law, user_context


def test_app_mounts_three_mcp_servers_at_stable_prefixes() -> None:
    mounts = {prefix: fmcp.name for prefix, fmcp in _MCP_MOUNTS}
    assert mounts == {
        "/mcp/swiss-law": "swiss-law-retrieval-mcp",
        "/mcp/contract-tools": "swiss-contract-tools-mcp",
        "/mcp/user-context": "swiss-user-context-mcp",
    }
    # Each prefix is reachable as an actual FastAPI route. We don't
    # call the MCP endpoint itself (that requires the streamable-HTTP
    # session handshake), but we DO assert the Mount node is wired —
    # which is the failure mode a missing ``app.mount`` would create.
    mounted_paths = {r.path for r in app.routes if hasattr(r, "path")}
    for prefix in mounts:
        assert prefix in mounted_paths, f"FastAPI app missing MCP mount {prefix!r}"


def test_mcp_base_url_derives_per_server_urls() -> None:
    s = Settings(mcp_base_url="https://swiss-legal.example.app")
    assert s.mcp_swiss_law_url == "https://swiss-legal.example.app/mcp/swiss-law/"
    assert s.mcp_contract_tools_url == "https://swiss-legal.example.app/mcp/contract-tools/"
    assert s.mcp_user_context_url == "https://swiss-legal.example.app/mcp/user-context/"


def test_mcp_base_url_does_not_overwrite_explicit_url() -> None:
    s = Settings(
        mcp_base_url="https://default.example.app",
        mcp_user_context_url="https://special.example.app/uc/",
    )
    # Per-server override wins over the base derivation.
    assert s.mcp_user_context_url == "https://special.example.app/uc/"
    # The other two still derive from the base.
    assert s.mcp_swiss_law_url == "https://default.example.app/mcp/swiss-law/"


@pytest.mark.asyncio
async def test_swiss_law_server_lists_expected_tools() -> None:
    fmcp = build_fastmcp(swiss_law.SERVER)
    names = sorted(t.name for t in await fmcp.list_tools())
    assert names == [
        "fetch_article_by_sr",
        "fetch_fedlex_article",
        "list_citations",
        "qdrant_search",
    ]


@pytest.mark.asyncio
async def test_swiss_law_server_invokes_list_citations() -> None:
    """End-to-end MCP invocation for the swiss_law server.

    ``list_citations`` is the one swiss_law tool that touches no
    network deps (no Qdrant, no embeddings) — passing an unknown
    entitlement id deterministically yields an empty list.
    """
    fmcp = build_fastmcp(swiss_law.SERVER)
    _content, structured = await fmcp.call_tool(
        "list_citations", {"entitlement_id": "__unknown_entitlement__"}
    )
    # FastMCP wraps a bare ``list[...]`` return as ``{"result": [...]}``.
    assert structured == {"result": []}


@pytest.mark.asyncio
async def test_contract_tools_server_invokes_score_confidence() -> None:
    """End-to-end MCP tool invocation through the FastMCP layer.

    ``score_confidence`` is the only contract tool that is pure
    (no Qdrant, no Anthropic) so it can run as a smoke check on every
    commit. Anything that returns the right shape here proves that
    the MCP protocol wrapping (argument validation, result coercion)
    works for the wrapper functions in ``contract_tools``.
    """
    fmcp = build_fastmcp(contract_tools.SERVER)
    # FastMCP returns ``(content_blocks, structured_content_dict)``
    # for tools that emit a dict — the structured payload is the
    # canonical decoding of the JSON the agent sees over the wire.
    _content, structured = await fmcp.call_tool(
        "score_confidence",
        {"raw_confidence": 0.95, "translation_only": True},
    )
    assert structured == {"confidence": 0.75, "capped": True}


@pytest.mark.asyncio
async def test_user_context_server_lists_expected_tools() -> None:
    fmcp = build_fastmcp(user_context.SERVER)
    names = sorted(t.name for t in await fmcp.list_tools())
    assert names == ["read_user_docs", "update_user_profile"]


@pytest.mark.asyncio
async def test_user_context_server_invokes_read_user_docs() -> None:
    """End-to-end MCP invocation for the user_context server.

    ``read_user_docs`` returns ``None`` for an unknown user_id without
    touching any external service, so it's a deterministic protocol-
    layer smoke test for this server.
    """
    fmcp = build_fastmcp(user_context.SERVER)
    content, _structured = await fmcp.call_tool("read_user_docs", {"user_id": "__unknown_user__"})
    # ``None`` returns are surfaced as a single text block "null"; we
    # don't bind to the exact wrapping, just to "tool ran and returned
    # the missing-user signal".
    text = "".join(getattr(b, "text", "") for b in content)
    assert text.strip() in {"null", ""}
