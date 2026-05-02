# Agent provenance schema (Task #25)

Every Claude inference call site in the Slaw_v3 backend must produce an
`AgentProvenance` record. The schema is the single contract that the
audit pipeline (CLI + `GET /admin/audits/agent-backed`) reads to answer:

> Was this analysis produced by a managed agent (sessions.events with
> ≥1 tool use), or by a plain `messages.create` completion?

## Where it lives

* Pydantic model: `swiss_legal_api.schemas.agent_provenance.AgentProvenance`
* Re-exported from `swiss_legal_api.schemas`
* Attached to:
  - `engine.verify.VerifyResult.agent_provenance` (always populated;
    the dataclass default builds a synthetic `messages.create` record
    so short-circuit paths never violate the contract)
  - `schemas.benefit_report.Benefit.agent_provenance` (defaulted to
    `None` so legacy persisted reports still validate; new scans
    always attach a real provenance)

## Fields

| field                  | meaning                                                                        |
| ---------------------- | ------------------------------------------------------------------------------ |
| `call_kind`            | `"messages.create"` (legacy) or `"sessions.events"` (managed agents).          |
| `agent_backed`         | True iff `call_kind=="sessions.events"` AND ≥1 tool/MCP-tool event observed.    |
| `model`                | Claude model identifier used for the call.                                     |
| `latency_ms`           | Wall-clock latency of the call.                                                |
| `input_tokens`         | From `resp.usage`, defaulted to 0 when usage is unavailable.                   |
| `output_tokens`        | Same.                                                                          |
| `agent_id`             | Managed-agent ID. `None` on the messages.create path.                          |
| `agent_version`        | Pinned agent version, if any.                                                  |
| `session_id`           | Managed-agents session ID, if any.                                             |
| `environment_id`       | Managed-agents environment ID, if any.                                         |
| `tools_offered`        | Tool / toolset names declared on the agent at session creation.                |
| `tool_use_count`       | Count of `agent.tool_use` events observed in the stream.                       |
| `mcp_tool_use_count`   | Count of `agent.mcp_tool_use` events observed in the stream.                   |
| `mcp_servers_invoked`  | Names of MCP servers whose tools were actually invoked.                        |

## Structured log line

Every Claude call emits exactly one `claude_call` log line with the
fields above plus a `site` tag:

```
claude_call site=engine.verify:tax_deduction_xyz call_kind=messages.create
  agent_backed=false model=claude-opus-4-7 latency_ms=812
  input_tokens=1124 output_tokens=87 tool_use_count=0 mcp_tool_use_count=0
```

This is the audit trail for `/chat` (and any future non-persisted call
site) where there is no `Benefit` row to inspect.

## Audit consumers

* `GET /admin/audits/agent-backed` (gated by `ADMIN_AUDIT_TOKEN` when
  set, 403 in production when unset).
* `python -m swiss_legal_api.audits agent_backed` — same JSON shape,
  for cron / CI.

Both call `swiss_legal_api.audits.agent_backed_summary()`, which walks
every persisted `BenefitReport.benefits[*].agent_provenance` and emits:

```json
{
  "total_benefits": N,
  "agent_backed": N_true,
  "unverified_by_agent": N_false,
  "unknown_provenance": N_legacy_null,
  "agent_backed_pct": float,
  "by_call_kind": {"messages.create": N, "sessions.events": N},
  "by_model": {...}
}
```

## Frontend signal

`frontend/components/BenefitCard.tsx` renders an "Unverified by agent"
amber pill when `b.agent_provenance?.agent_backed === false` (or when
the field is missing on a legacy snapshot). The badge is non-blocking
— the benefit is still presented in full — and disappears the moment a
benefit is verified through the managed-agents path.
