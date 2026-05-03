# Managed Agents — operator setup

This doc covers the one-time provisioning needed to flip the backend
from the `messages.create` path to the Claude Managed Agents path
(`engine.agent_runner.run_session`). It only stands the environment
up — the actual flip of `USE_MANAGED_AGENTS=1` and any code that
takes advantage of the new path are tracked in follow-up tasks.

## Prerequisites

- `ANTHROPIC_API_KEY` is set as a Replit Secret. The bootstrap and
  the runtime both read it from the process env.
- The app is deployed (or is reachable on a stable public HTTPS URL).
  Anthropic's agent runtime calls the three MCP servers from outside
  this container, so a `localhost` or `*.repl.co` dev URL is only
  acceptable for ad-hoc smoke tests.

## Step 1 — wire the MCP base URL

The three FastMCP servers are co-mounted under the FastAPI app at:

| Server                    | Mount path             |
| ------------------------- | ---------------------- |
| `swiss-law-retrieval-mcp` | `/mcp/swiss-law/`      |
| `swiss-contract-tools-mcp`| `/mcp/contract-tools/` |
| `swiss-user-context-mcp`  | `/mcp/user-context/`   |

Set a single shared env var so `Settings.model_post_init` derives the
three per-server URLs automatically:

```
MCP_BASE_URL=https://<your-deployment-host>
```

For per-server overrides (e.g. one MCP runs in a different region),
set `MCP_SWISS_LAW_URL`, `MCP_CONTRACT_TOOLS_URL`, or
`MCP_USER_CONTEXT_URL` directly — the per-server value wins.

Optional bearer tokens for outbound MCP auth (registered into the
vault by the bootstrap when present):

```
MCP_SWISS_LAW_AUTH_TOKEN=...
MCP_CONTRACT_TOOLS_AUTH_TOKEN=...
MCP_USER_CONTEXT_AUTH_TOKEN=...
```

## Step 2 — provision agent + environment + vault

Always start with a dry run to inspect the payload Anthropic will
receive (credentials are redacted in dry-run output):

```bash
cd backend
PYTHONPATH=src python -m swiss_legal_api.managed_agents.bootstrap --dry-run
```

Then run the live bootstrap. Pass `--no-write-env` so the IDs go to
Replit Secrets / shared env vars instead of a checked-in `.env`, and
`--out` so a wrapper can pick them up:

```bash
PYTHONPATH=src python -m swiss_legal_api.managed_agents.bootstrap \
    --no-write-env --out /tmp/managed-ids.json
```

The script prints four `MANAGED_*=<id>` lines and writes the same
mapping as JSON to `/tmp/managed-ids.json`. Register them as **shared
env vars** (they're identifiers, not credentials) — open the Replit
Secrets pane and add:

- `MANAGED_AGENT_ID`
- `MANAGED_AGENT_VERSION`
- `MANAGED_ENVIRONMENT_ID`
- `MANAGED_VAULT_ID`

The bootstrap is **re-runnable**: when `MANAGED_AGENT_ID` is already
set in the env, it issues `PUT /v1/agents/{id}` with the current
`version` instead of creating a duplicate. Existing environment and
vault IDs are reused as-is.

## Step 3 — smoke test

After restarting the workflow so the new env vars are in scope, run:

```bash
cd backend
PYTHONPATH=src python scripts/managed_agents_smoke.py
```

It opens one session, asks a trivial Swiss-law question, and exits
non-zero with a precise reason if anything is mis-wired. A successful
run logs the `mcp_tool_use_count` (must be ≥ 1) and the agent's
short answer.

Exit codes: `0` ok, `1` config missing, `2` no MCP tool used (likely
a mis-set `MCP_BASE_URL` or an MCP mount returning non-200),
`3` fatal session error, `4` unexpected exception.

## Step 4 — flip the runtime path

Out of scope for this task — see the follow-up "Make Managed Agents
the scan driver" and "Default to Managed Agents and stream tool
calls" tasks. When you're ready, set `USE_MANAGED_AGENTS=1` and
restart.

## Rollback

`USE_MANAGED_AGENTS=0` (or unset) immediately restores the
`messages.create` path; the four `MANAGED_*` IDs and the MCP env
vars stay populated but are not consulted, so a rollback never
requires deleting any vendor-side resources.
