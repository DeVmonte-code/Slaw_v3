# Managed Agents — Operator Guide

Slaw v3 ships with two verification paths:

| Mode | Flag | `call_kind` | `agent_backed` | Tool use |
|---|---|---|---|---|
| **Managed Agents** (production) | `USE_MANAGED_AGENTS=1` | `sessions.events` | `true` | ≥1 MCP call per entitlement |
| **messages.create** (dev/CI) | `USE_MANAGED_AGENTS=0` | `messages.create` | `false` | none |

The runtime auto-selects: if `MANAGED_AGENT_ID` **and** `MANAGED_AGENT_VERSION` are set in the environment, `use_managed_agents` defaults to `True`. If either is missing, it defaults to `False` with a startup warning. Explicitly overriding with `USE_MANAGED_AGENTS=0` forces the fallback path regardless of which IDs are present.

---

## 1. Prerequisites

- `ANTHROPIC_API_KEY` with Managed Agents access (contact Anthropic if the beta is not yet enabled on your key).
- `MCP_BASE_URL` set to the public HTTPS hostname of the running API — used to auto-derive the three per-server URLs below. On Replit, this is `https://<repl-slug>.replit.dev` (or the custom domain).
- Optional per-server auth tokens in env (see §5).

---

## 2. Bootstrap (one-time per cluster)

The bootstrap creates the agent, environment, and vault in one shot and writes the four resulting IDs back to `backend/.env` (or prints them for Replit Secrets):

```bash
cd backend

# Dry-run: print the JSON payloads without POSTing
python -m swiss_legal_api.managed_agents.bootstrap --dry-run

# Live run + write IDs to backend/.env
MCP_BASE_URL=https://<your-host> python -m swiss_legal_api.managed_agents.bootstrap

# On Replit (IDs go into Secrets, not .env)
MCP_BASE_URL=https://<your-host> \
python -m swiss_legal_api.managed_agents.bootstrap \
  --no-write-env \
  --out /tmp/managed_ids.json
# Then paste the four values from /tmp/managed_ids.json into Replit Secrets.
```

The script is idempotent: if `MANAGED_AGENT_ID` is already set, it issues a `PUT /v1/agents/{id}` (version bump) instead of a `POST`.

---

## 3. Agent identity

| Field | Value |
|---|---|
| **Name** | `SwissLegalBenefitScanner` |
| **Model** | `CLAUDE_MODEL` env var (default `claude-sonnet-4-6`) |
| **System prompt** | `managed_agents/bootstrap.py:SYSTEM_PROMPT` — mirrors `engine/verify.py:SYSTEM` |
| **Metadata** | `{"app": "slaw_v3", "task": "26"}` |

---

## 4. MCP server bindings and tool allow-list

Three servers are registered. The URL for each is derived from `MCP_BASE_URL` unless overridden individually.

| Server | Auto-derived URL | Override env var | Permission |
|---|---|---|---|
| `swiss-law-retrieval-mcp` | `{MCP_BASE_URL}/mcp/swiss-law` | `MCP_SWISS_LAW_URL` | `always_allow` — pure retrieval |
| `swiss-contract-tools-mcp` | `{MCP_BASE_URL}/mcp/contract-tools` | `MCP_CONTRACT_TOOLS_URL` | `always_ask` — analysis tools |
| `swiss-user-context-mcp` | `{MCP_BASE_URL}/mcp/user-context` | `MCP_USER_CONTEXT_URL` | `always_ask` — user writes |

**Write / shell tools are `always_ask`** — the runner's `requires_action` loop must explicitly confirm them. `bash` is also `always_ask`. No tool in the allow-list can delete data or make external network requests outside the `network_allowlist` defined in the environment.

---

## 5. Environment variables reference

| Var | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key with Managed Agents access |
| `MCP_BASE_URL` | ✅ bootstrap | Public HTTPS base for auto-deriving MCP URLs |
| `MANAGED_AGENT_ID` | ✅ runtime | Agent ID returned by bootstrap |
| `MANAGED_AGENT_VERSION` | ✅ runtime | Agent version (integer) returned by bootstrap |
| `MANAGED_ENVIRONMENT_ID` | ✅ runtime | Environment ID returned by bootstrap |
| `MANAGED_VAULT_ID` | ✅ runtime | Vault ID returned by bootstrap |
| `USE_MANAGED_AGENTS` | optional | Force `1`/`0`; auto-derived from IDs when absent |
| `MANAGED_AGENT_ID_DEV` / `_PROD` | optional | Per-environment overrides; merged into `MANAGED_AGENT_ID` by `Settings` |
| `MANAGED_AGENT_VERSION_DEV` / `_PROD` | optional | Per-environment version counterparts |
| `MCP_SWISS_LAW_URL` | optional | Override auto-derived swiss-law URL |
| `MCP_CONTRACT_TOOLS_URL` | optional | Override auto-derived contract-tools URL |
| `MCP_USER_CONTEXT_URL` | optional | Override auto-derived user-context URL |
| `MCP_SWISS_LAW_AUTH_TOKEN` | optional | Bearer token stored in vault for swiss-law server |
| `MCP_CONTRACT_TOOLS_AUTH_TOKEN` | optional | Bearer token stored in vault for contract-tools server |
| `MCP_USER_CONTEXT_AUTH_TOKEN` | optional | Bearer token stored in vault for user-context server |

Store all `MANAGED_*` values in **Replit Secrets** (or a secrets manager). Never commit them to `.env` or `start.sh`.

---

## 6. Startup validation

On every boot, `api/main.py:_validate_managed_agents_config()` runs before the app accepts traffic. When `use_managed_agents=True`:

- It checks all four IDs **and** the three MCP URLs are non-empty.
- If anything is missing it raises `RuntimeError` with an explicit list of the missing variables — the deploy crashes loudly rather than degrading silently.
- On success it logs `agent_runner_ready agent_id=<redacted> version=N ...` so ops can confirm which agent the process is bound to.

When `use_managed_agents=False` it logs `agent_runner_unconfigured` (WARNING level) so the fallback is always visible in logs.

---

## 7. Version-bump procedure

Re-run bootstrap whenever the system prompt or tool allow-list changes:

```bash
# Ensure existing MANAGED_AGENT_ID is exported so bootstrap does a PUT (not POST)
MCP_BASE_URL=https://<your-host> \
python -m swiss_legal_api.managed_agents.bootstrap --no-write-env --out /tmp/managed_ids.json
# Update MANAGED_AGENT_VERSION in Replit Secrets to the new value
# Restart the workflow — lifespan will log agent_runner_ready with new version
```

---

## 8. Acceptance gate

After any deploy, run the acceptance gate to confirm 100% of verifications are agent-backed:

```bash
cd backend
SCAN_JOB_ID=<generated_at_iso> python scripts/check_agent_backed.py
```

The gate queries `/admin/audits/agent-backed?job_id=<SCAN_JOB_ID>`, asserts `total_benefits >= 5` and `agent_backed_pct == 100.0`, and exits non-zero on failure. It is also wired into `scripts/smoke.sh` (line 90) so a CI run that downgrades any verification to `messages.create` fails before reaching users.

To drill into a failing gate run:

```bash
curl "$API_BASE_URL/admin/audits/agent-backed?details=true&job_id=<SCAN_JOB_ID>"
```

The `records` array lists every persisted verification with its `call_kind`, `agent_backed`, `tool_use_count`, and `mcp_servers_invoked` so you can identify exactly which entitlement fell back and why.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `agent_runner_unconfigured` in boot log | IDs missing or `USE_MANAGED_AGENTS=0` | Run bootstrap, add IDs to Secrets, restart |
| `RuntimeError: USE_MANAGED_AGENTS=true but required configuration is missing` | IDs present but one MCP URL empty | Set `MCP_BASE_URL` or the individual `MCP_*_URL` vars |
| `agent_backed_pct=0.0` after a scan | Scans aren't being persisted to DB | Only `/users/{id}/profile → /scan` flows persist; bare `/scan` calls don't |
| `tool_use_count=0` despite `agent_backed=true` | Agent decided retrieval wasn't needed | Check Qdrant collection health at `/readyz?deep=1` |
| 401 / 403 from MCP server | Auth token missing from vault | Set `MCP_*_AUTH_TOKEN` env vars and re-run bootstrap to register them |
