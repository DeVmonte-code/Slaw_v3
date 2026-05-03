"""Three MCP servers backing the Managed Agents pipeline (Task #26).

Each server is a thin protocol wrapper around shared callables that
already live in ``swiss_legal_api`` modules. Both the legacy
``messages.create`` path (Config A) and the managed-agents path
(Config B) resolve to the SAME Python objects — the registry below
is the single source of truth that the SSOT regression test
(``tests/test_mcp_single_source_of_truth.py``) asserts on.

Why a registry instead of three free-standing FastMCP modules:
- We can build & test the wiring without taking a hard dep on the
  ``mcp`` Python SDK. The optional ``serve()`` shims at the bottom of
  each server module use ``mcp`` only when the server is actually
  hosted, keeping the import surface clean for unit tests.
- The audit (Task #25) cares about *which* tools were invoked, not
  the protocol they were invoked over, so the registry's tool names
  match exactly what the runner will see in
  ``agent.mcp_tool_use.name`` events.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from mcp.server.fastmcp import FastMCP


@dataclass(frozen=True)
class McpToolSpec:
    """One MCP tool exported by a server.

    ``impl`` is the *exact* Python callable that the MCP runtime will
    invoke. The SSOT test imports the original module and asserts
    ``impl is <module>.<name>`` so a future refactor that copies the
    function instead of re-exporting it fails loudly.
    """

    name: str
    description: str
    impl: Callable[..., object]


@dataclass(frozen=True)
class McpServerSpec:
    """One MCP server's contract: stable name + tool list."""

    name: str
    tools: tuple[McpToolSpec, ...]


def build_fastmcp(spec: "McpServerSpec", *, mount_path: str = "/") -> "FastMCP":
    """Construct a configured ``FastMCP`` from a registry spec.

    Used by both the standalone ``serve()`` shims and the FastAPI mount
    helper (``swiss_legal_api.api.main``) so the wire-level wiring lives
    in one place. ``mount_path="/"`` makes the streamable-HTTP endpoint
    reachable at the root of the server (or sub-mount), which is what
    ``Settings.mcp_base_url``-derived URLs assume.
    """
    from mcp.server.fastmcp import FastMCP

    app = FastMCP(spec.name, streamable_http_path=mount_path)
    for tool in spec.tools:
        app.tool(name=tool.name, description=tool.description)(tool.impl)
    return app


__all__ = ["McpServerSpec", "McpToolSpec", "build_fastmcp"]
