# Audit findings — Managed Agents production verification (Task #30)

Date opened: 2026-05-02
Status: **AWAITING PROD FLIP** — operator action required (see below).

## Purpose

Task #26 added the managed-agents pipeline behind `USE_MANAGED_AGENTS`,
defaulted off. Task #30 is the verification gate: confirm the flag is
actually flipped in production, that real `/scan` and `/chat` traffic is
routed through Claude Managed Agents (not the legacy `messages.create`
fallback), and that every new verification call uses the MCP tools
(`agent_backed ≈ 100%`).

## Operator handoff — what's done in dev vs what you must do in prod

### Done in dev (this commit)
- Bootstrap script confirmed runnable end-to-end via
  `PYTHONPATH=src python -m swiss_legal_api.managed_agents.bootstrap --dry-run`.
  The rendered agent payload uses the documented per-doc schema:
  `default_config.permission_policy=always_allow` plus a per-tool
  `configs[{tool_name: "bash", permission_policy: always_ask}]`
  override. No legacy `permission_policies` map.
- Audit CLI confirmed runnable:
  `PYTHONPATH=src python -m swiss_legal_api.audits agent_backed --details`.
  In dev (empty BenefitReport store) it returns
  `{"total_benefits": 0, "agent_backed": 0, "agent_backed_pct": 0.0}` —
  the expected baseline for a fresh database.
- `engine/agent_runner.py` regression suite covers the four blocking
  managed-session correctness gaps (177 backend tests pass):
  retryable vs fatal `session.error`, fatal-after-partial-text fail-
  safe, `requires_action` confirmation loop, `{task_type, user_id}`
  metadata.

### Operator action — required before re-running the audit

1. Stand up the three MCP servers behind HTTPS (Task #31 covers the
   deployment). Capture the URLs.
2. Set the following secrets in the Replit deployment (NOT in dev):
   - `MCP_SWISS_LAW_URL`
   - `MCP_CONTRACT_TOOLS_URL`
   - `MCP_USER_CONTEXT_URL`
   - (recommended) per-server bearer tokens
     `MCP_SWISS_LAW_AUTH_TOKEN`, `MCP_CONTRACT_TOOLS_AUTH_TOKEN`,
     `MCP_USER_CONTEXT_AUTH_TOKEN`
3. From a shell with the prod `ANTHROPIC_API_KEY` and the MCP URLs
   loaded, run:
   ```bash
   PYTHONPATH=src python -m swiss_legal_api.managed_agents.bootstrap
   ```
   The script POSTs the agent + environment + vault and writes the
   resulting IDs back to `.env`. Copy the four resulting values into
   the deployment secrets:
   - `MANAGED_AGENT_ID`
   - `MANAGED_AGENT_VERSION`
   - `MANAGED_ENVIRONMENT_ID`
   - `MANAGED_VAULT_ID`
4. Set `USE_MANAGED_AGENTS=true` in the deployment.
5. Redeploy. Smoke-test by hitting `/scan` once with a known profile
   and `/chat` with a known `benefit_id`.

### Operator action — re-run the agent on this task

Once the flag is flipped and at least one /scan + /chat round-trip has
landed, re-run me on Task #30. I'll fill in the **Post-flip
measurements** section below with real numbers from
`python -m swiss_legal_api.audits agent_backed --details=true`
against the production database, attach the structured
`claude_call` log lines for one verify and one chat call, and close
the task.

## Post-flip measurements (TO BE FILLED ON RE-RUN)

### Audit CLI output (production DB)

```text
PLACEHOLDER — paste the JSON output of:
  PYTHONPATH=src python -m swiss_legal_api.audits agent_backed \
      --since=<flip-timestamp> --details=true
```

Expected shape:
- `total_benefits`: > 0 (at least one post-flip /scan)
- `agent_backed_pct`: ≈ 100.0 for every record at or after
  `<flip-timestamp>`
- `by_call_kind`: dominated by `sessions.events`; any residual
  `messages.create` is a regression — investigate before closing.

### Sample structured log lines

```text
PLACEHOLDER — paste two lines from the API logs:
  1. one engine.verify:<ent_id> claude_call line
  2. one api.chat:<benefit_id> claude_call line
Both must contain:
  - call_kind=sessions.events
  - agent_backed=true
  - mcp_tool_use_count > 0
  - session_id=sess_…
  - agent_id=<MANAGED_AGENT_ID>
  - mcp_servers_invoked containing at least swiss-contract-tools-mcp
    (verify) or swiss-law-retrieval-mcp (chat)
```

### Failure-mode dry-run (optional but recommended)

If you want to prove the operator-grep path works for an MCP auth
failure: temporarily revoke one MCP bearer token, hit /scan, and
confirm a `managed_session_error` warning appears with `session_id`,
`retry_status`, `mcp_server`, and `mcp_tool` populated. Restore the
token afterwards.

## Done criteria (from task-30.md)

- [x] Bootstrap script verified runnable (dry-run; full run is
      operator-side).
- [ ] Bootstrap run once in production → IDs persisted to `.env`
      (operator).
- [ ] `USE_MANAGED_AGENTS=true` in production deployment (operator).
- [ ] `agent_backed ≈ 100%` measured across post-flip `/scan` and
      `/chat` traffic (re-run agent to fill).
- [x] Audit findings file created under `backend/doc/audits/`
      (this file).
