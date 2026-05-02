"""Provenance schema for every Claude inference call site.

Task #25 — Audit & prove the IA analysis is agent-backed.

The schema is the contract the audit pipeline reads. Every Claude call
in the codebase MUST attach an :class:`AgentProvenance` record to its
output, so we can answer one question per persisted result:

    "Was this analysis produced by a managed agent (sessions.events
    with ≥1 tool use), or by a plain ``messages.create`` completion?"

The current call sites all use ``messages.create``, which means the
baseline is ``call_kind="messages.create"`` and ``agent_backed=False``.
Task #26 will flip the call sites to managed agents; this task locks
the contract and emits the structured ``claude_call`` log so the
managed-agents migration can be proven (not asserted) end-to-end.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CallKind = Literal["messages.create", "sessions.events"]


class AgentProvenance(BaseModel):
    """Structured provenance record attached to every Claude call output.

    Persisted with each verified ``Benefit`` (so historical scans can be
    audited) and emitted as a single-line ``claude_call`` log event (so
    even non-persisted call sites — ``/chat`` — leave an audit trail).

    ``agent_backed`` is the headline signal: it is True iff the call was
    routed through the managed-agents API *and* the resulting session
    actually emitted at least one ``agent.tool_use`` or
    ``agent.mcp_tool_use`` event. A ``sessions.events`` call that never
    used a tool is still ``agent_backed=False`` — that's the whole point
    of the audit.
    """

    call_kind: CallKind = Field(
        ...,
        description=(
            "Which Anthropic surface produced this output. "
            "'messages.create' is the legacy completion path; "
            "'sessions.events' is the managed-agents path."
        ),
    )
    agent_backed: bool = Field(
        ...,
        description=(
            "True iff call_kind=='sessions.events' AND the session "
            "emitted ≥1 agent.tool_use or agent.mcp_tool_use event."
        ),
    )
    model: str = Field(..., description="Claude model identifier used for the call.")
    latency_ms: int = Field(..., ge=0, description="Wall-clock latency of the call.")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    # Managed-agents-only fields. Defaulted to None so the
    # messages.create baseline serialises cleanly.
    agent_id: str | None = Field(
        default=None,
        description="Managed agent ID (None on the messages.create path).",
    )
    agent_version: int | None = Field(
        default=None,
        description="Pinned agent version, if any.",
    )
    session_id: str | None = Field(
        default=None,
        description="Managed-agents session ID, if any.",
    )
    environment_id: str | None = Field(
        default=None,
        description="Managed-agents environment ID, if any.",
    )
    tools_offered: list[str] = Field(
        default_factory=list,
        description=(
            "Tool / toolset names declared on the agent at session "
            "creation. Empty on the messages.create path."
        ),
    )
    tool_use_count: int = Field(
        default=0,
        ge=0,
        description="Number of agent.tool_use events observed in the stream.",
    )
    mcp_tool_use_count: int = Field(
        default=0,
        ge=0,
        description="Number of agent.mcp_tool_use events observed in the stream.",
    )
    mcp_servers_invoked: list[str] = Field(
        default_factory=list,
        description="Names of MCP servers whose tools were actually invoked.",
    )
