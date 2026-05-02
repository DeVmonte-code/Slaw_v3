# Agent-backed audit — baseline (2026-05)

Task #25 instruments every Claude call site in the Slaw_v3 backend and
asks the audit pipeline one question:

> Of every analysis we have shipped to a user, what fraction was
> produced by a managed Anthropic agent (`sessions.events` with at
> least one `agent.tool_use` or `agent.mcp_tool_use` event)?

This is the baseline finding. Task #26 will flip the call sites; the
same audit will then prove the migration without manual review.

## Headline

**0 % agent-backed.** Every persisted `Benefit.agent_provenance` has
`call_kind="messages.create"` and `agent_backed=False`. There is no
managed-agents path in the codebase yet.

The audit endpoint and CLI now report this number; a regression test
in `tests/test_agent_provenance.py` asserts the baseline so a silent
"oops we shipped messages.create everywhere" can't happen twice.

## Code paths still on `messages.create`

Two call sites instantiate `anthropic.AsyncAnthropic` and call
`messages.create` directly:

| call site                              | persisted? | provenance trail                              |
| -------------------------------------- | ---------- | --------------------------------------------- |
| `swiss_legal_api.engine.verify._call_claude` | Yes — written into `Benefit.agent_provenance` and into the SQLite `scan_results` row | structured `claude_call site=engine.verify:<entitlement_id>` log + persisted record |
| `swiss_legal_api.api.chat._call_claude`      | No — `/chat` answers are returned and forgotten                                    | structured `claude_call site=api.chat:<benefit_id\|no_benefit>` log only |

Both sites build the same `AgentProvenance` shape so the audit can
report them under one `by_call_kind` bucket.

## Gap checklist vs. the managed-agents reference (Config B)

To move the headline above zero we need each of the following from
`backend/doc/Claude Managed Agents overview/`:

* **Define your agent** — register a versioned agent with the SR
  retrieval / verification toolset and the swiss-law and
  contract-tools MCP server names declared. (See
  `Define your agent.md`.)
* **Environments** — create one per deploy stage so the verifier can
  isolate state, file system, and bash from `/chat`'s read-only
  follow-up environment.
* **Start a session** — replace `messages.create` with
  `client.beta.sessions.create(agent=..., environment_id=...,
  vault_ids=...)`, pinning agent version in production. (See
  `Start a session.md`.)
* **Send + stream events** — open the `sessions.events.stream` first,
  send a `user.message`, drain `agent.tool_use`,
  `agent.mcp_tool_use`, `span.model_request_end` events, and stop
  on `session.status_idle`. (See `Session event stream.md`.)
* **MCP connector** — wire `swiss-law` and `contract-tools` MCP
  servers into the agent definition; keep the URLs in
  `mcp_servers[]` and the credentials in a vault referenced at
  session creation. (See `MCP connector.md`.)
* **Permission policies** — auto-approve trusted internal MCP tools
  via `default_config.permission_policy=always_allow`; leave
  user-side write tools on `always_ask`. (See
  `Permission policies.md`.)

For each session we capture: `session_id`, `agent_id`, `agent_version`,
`environment_id`, the `tools_offered` list at agent-creation time, the
observed `tool_use_count` and `mcp_tool_use_count`, and the set of MCP
servers whose tools were actually invoked. The schema is in
`backend/doc/audits/agent_provenance.md`.

## How to verify the baseline locally

```bash
# 1. Run a scan against a real (or fixture) profile, then:
python -m swiss_legal_api.audits agent_backed | jq

# Expected today:
# {
#   "agent_backed": 0,
#   "agent_backed_pct": 0.0,
#   "by_call_kind": {"messages.create": <N>},
#   ...
# }

# 2. Or hit the endpoint (X-Admin-Token required when
# ADMIN_AUDIT_TOKEN is set; in dev it's open).
curl -s http://localhost:8000/admin/audits/agent-backed | jq
```

When Task #26 lands, `agent_backed_pct` should climb without any
change to this audit code — the same dict shape, the same counts,
just routed through `sessions.events`.
