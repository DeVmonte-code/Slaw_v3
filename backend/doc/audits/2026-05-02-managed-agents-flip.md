# Audit findings — Managed Agents flip (Task #26)

Date: 2026-05-02

## What shipped

Task #26 swaps every `_call_claude` call site (`engine/verify.py` and
`api/chat.py`) from `messages.create` to a managed-agents session,
gated by the new `settings.use_managed_agents` flag. The supporting
pieces:

- Three MCP servers under `swiss_legal_api/mcp_servers/`
  (`swiss-law-retrieval-mcp`, `swiss-contract-tools-mcp`,
  `swiss-user-context-mcp`). Each one is a thin protocol wrapper
  around shared callables — the SSOT regression test
  (`tests/test_mcp_single_source_of_truth.py`) asserts identity
  between the registry's `impl` and the canonical Python function so
  Config A and Config B can never silently drift.
- One-shot `python -m swiss_legal_api.managed_agents.bootstrap` that
  provisions the agent (`SwissLegalBenefitScanner`), environment, and
  vault, then writes the resulting IDs back to `backend/.env`.
- `engine/agent_runner.py` opens the SSE stream first, sends the
  `user.message` event, consumes events until `session.status_idle`,
  and returns `(text, AgentProvenance)` with `call_kind="sessions.events"`
  populated. `agent_backed` is True iff `tool_use_count +
  mcp_tool_use_count > 0` — exactly the truth function the schema's
  `model_validator` enforces.

## How the audit will flip

Run the Task #25 audit before and after flipping
`use_managed_agents=true` on a deploy that has the bootstrap IDs and
all three MCP URLs configured:

```bash
python -m swiss_legal_api.audits agent_backed --details=true
```

Pre-flip baseline: `agent_backed=0%` for every persisted Benefit
because every record carries `call_kind="messages.create"`.

Post-flip target: `agent_backed≈100%` for every NEW verification.
Existing rows do not retroactively change — the audit aggregates over
persisted history, and historical Benefits keep their original
provenance. The follow-up task to tighten the API to a hard gate
(reject persisting any `Benefit` with `agent_backed=False` for new
scans) should wait one full retention window so the audit can confirm
the flip is stable across at least one nightly sweep cycle.

## Operator runbook (deploy-time)

1. Stand up the three MCP servers behind HTTPS. Set:
   - `MCP_SWISS_LAW_URL`
   - `MCP_CONTRACT_TOOLS_URL`
   - `MCP_USER_CONTEXT_URL`
2. `python -m swiss_legal_api.managed_agents.bootstrap` — the script
   POSTs the agent + environment + vault and writes
   `MANAGED_AGENT_ID`, `MANAGED_AGENT_VERSION`, `MANAGED_ENVIRONMENT_ID`,
   `MANAGED_VAULT_ID` back to `.env`.
3. Restart the API.
4. Set `USE_MANAGED_AGENTS=true` and restart again.
5. Trigger one `/scan`, then run the audit CLI to confirm
   `agent_backed=true` on the new Benefit.
6. Watch `claude_call` log lines for `call_kind=sessions.events` —
   every line should now carry `session_id`, `agent_id`, and at least
   one `mcp_servers_invoked` entry per verify.

## Failure modes

- `ManagedAgentsConfigError` at request time → bootstrap was not
  completed (or the `.env` was not picked up). Fix: re-run bootstrap
  and restart.
- `ManagedAgentsError: session_terminated` → the agent's environment
  hit a terminal error (network allowlist, MCP auth, container
  crash). Check the structured `agent_stream_*` warnings around the
  failed `session_id`.
- MCP auth failure on `vault_ids` → session is created but the
  `session.error` event with `retry_status` describes the missing
  credential; re-register it via the vaults API.

## Out of scope (intentional)

- Backfilling old Benefits with new provenance — historical
  `messages.create` rows stay as-is so the audit timeline reflects the
  real production posture per period.
- Hard-gating the API on `agent_backed=true` — separate, much smaller
  follow-up after the flip is observed stable for one retention
  window.
