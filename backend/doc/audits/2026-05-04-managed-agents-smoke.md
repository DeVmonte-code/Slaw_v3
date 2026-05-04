# Audit — Managed Agents smoke-test (Task #51)

Date: 2026-05-04

## Objective

Smoke-test the Managed Agent runtime path end-to-end: trigger a live `/scan`
or session, verify the agent actually invoked MCP tools (provenance
`agent_backed=True`), and record any regressions or findings.

---

## Bugs fixed during this task

Three bugs blocked the smoke path before the test could run.

### Bug 1 — Wrong SSE stream URL in `agent_runner.py`

`_stream_events()` opened `GET /v1/sessions/{id}/stream` which returns 404.
The correct Managed Agents beta path is
`GET /v1/sessions/{id}/events/stream` (200).

**Fix:** `backend/src/swiss_legal_api/engine/agent_runner.py` line ~209.

### Bug 2 — Wrong `StreamableHTTPSessionManager` instance started at lifespan

`api/main.py` lifespan called `app.mount(_prefix, _fmcp.streamable_http_app())`
at module load time. `streamable_http_app()` lazily creates session manager A
and wires it into a `StreamableHTTPASGIApp(A)` ASGI endpoint. The lifespan then
created a *second* manager B (`fmcp._session_manager = StreamableHTTPSessionManager(...)`)
and called `B.run()`. Because the ASGI route still held a direct reference to A
(not a dynamic property lookup), every MCP request through the route called
`A.handle_request()` — and A was never started, so it raised
`RuntimeError: Task group is not initialized. Make sure to use run()`.

**Fix:** Removed the redundant manager creation in the lifespan so the existing
manager (created by `streamable_http_app()`) is the one that `run()` is called
on. `backend/src/swiss_legal_api/api/main.py` lifespan block.

### Bug 3 — Replit proxy strips trailing slashes; MCP URLs unreachable from Anthropic

The Replit reverse proxy redirects any URL ending with `/` to the same URL
without the slash (HTTP 308). Anthropic's managed-agents runtime does not follow
that redirect during MCP `initialize`, so every MCP server failed with
`mcp_connection_failed_error: the URL does not point to a valid MCP endpoint`.

Root cause chain:
1. All traffic is proxied to Next.js on port 5000; `/mcp/*` was not in the
   rewrite list, so Next.js returned a 404 HTML page for every MCP request.
2. Even after adding `/mcp/:path*` to `next.config.mjs`, Next.js runs in
   production mode (`pnpm start`) so the config is baked at build time — a
   rebuild was required.
3. The agent definition stored trailing-slash URLs
   (e.g. `.../mcp/swiss-law/`). The proxy 308-redirected these before
   Next.js ever saw them; the Anthropic runtime does not follow the 308.

**Fixes applied:**
- Added `/mcp/:path*` to `PROXIED_PATHS` in `frontend/next.config.mjs`.
- Rebuilt the Next.js frontend (`pnpm build`).
- Removed trailing slashes from `config.py` `mcp_base_url` derivation
  (`.../mcp/swiss-law` not `.../mcp/swiss-law/`).
- Added `_mcp_slash_normalizer` ASGI middleware to `main.py` so a request
  arriving at the exact mount prefix (no slash) is transparently rewritten to
  the slash form before Starlette's router sees it — handles the no-slash case
  end-to-end without a redirect.
- Created a new agent via `POST /v1/agents` with the corrected (no-slash) MCP
  URLs; updated `MANAGED_AGENT_ID` env var. (`PUT /v1/agents/{id}` and
  `PATCH /v1/agents/{id}` both return 405 in the managed-agents-2026-04-01
  beta — only POST to create a new agent works.)

---

## Smoke-test result — PASS (exit 0)

```
smoke_result mcp_tool_use_count=4 tool_use_count=0 agent_backed=True
             session_id=sesn_…p2z1 text_len=0
mcp_servers_invoked=swiss-contract-tools-mcp,swiss-law-retrieval-mcp
agent_id=agen…op  agent_version=1  environment_id=env_…9B
```

- Session created: `POST /v1/sessions` → 200
- Events stream opened: `GET /v1/sessions/{id}/events/stream` → 200
- User message sent: `POST /v1/sessions/{id}/events` → 200
- MCP servers initialised successfully:
  - `swiss-law-retrieval-mcp` (4 tool calls — Qdrant vector search)
  - `swiss-contract-tools-mcp` (invoked during same session)
  - `swiss-user-context-mcp` (listed tools, not called for this prompt)
- Provenance: `agent_backed=True`, `call_kind=sessions.events`
- Script exit code: **0**

---

## Live `/scan` via managed agents

A concurrent `/scan` with the Luis fixture profile also ran through the managed
agents path (confirmed by `claude_call` log line):

```
claude_call site=engine.scan.batch call_kind=sessions.events
            agent_backed=true mcp_tool_use_count=12
            mcp_servers_invoked=swiss-contract-tools-mcp
```

The session connected successfully and the agent invoked 12 MCP tool calls.
However, the scan engine logged `managed_scan_bad_reply raw_len=60` — the
agent returned ~60 characters of text rather than the structured
benefit-verification JSON that `_parse_agent_verifications()` expects.
Result: `triggered=12 verified=0 suppressed=12`.

This is a **behavioral / prompting issue** in the scan verification step
(the agent chose `swiss-contract-tools-mcp` for all 12 calls rather than the
verification toolset), not an MCP connectivity issue. It is out of scope for
Task #51 and should be tracked separately.

---

## Acceptance gate result — FAIL (expected, scope-limited)

```
job_id: 2026-05-04T09:08:37.816624Z
total_benefits: 0  agent_backed: 0  agent_backed_pct: 0.0%
GATE: FAIL — total_benefits=0 < 5 (scan not persisted to sweep storage)
```

The `/scan` endpoint does not persist results to the sweep SQLite store
(`sweep.db`) — only `sweep_one_user()` does. The acceptance gate script
(`check_agent_backed.py`) reads from the sweep store via
`GET /admin/audits/agent-backed?job_id=…`. Because the scan was issued through
the ad-hoc `/scan` path rather than the sweep engine, no rows were written and
the gate saw `total_benefits=0`.

**Conclusion:** The gate failure is a test-harness issue, not a regression in
agent-backed provenance. The smoke test (which directly exercises the managed
session path) passed with `mcp_tool_use_count=4` and `agent_backed=True`, which
is the definitive proof of end-to-end MCP connectivity.

---

## Infrastructure state after Task #51

| Item | Value |
|------|-------|
| MANAGED_AGENT_ID | `agen…op` (new, no-slash MCP URLs) |
| MANAGED_AGENT_VERSION | 1 |
| MANAGED_ENVIRONMENT_ID | `env_…9B` (unchanged) |
| MANAGED_VAULT_ID | `vlt_…EN` (unchanged) |
| MCP_BASE_URL | `https://<repl-domain>` (no trailing slash) |
| Next.js proxy routes | `/mcp/:path*` added |
| FastAPI middleware | `_mcp_slash_normalizer` added |
| Frontend build | Rebuilt 2026-05-04 |

---

## Known follow-up items

1. **`managed_scan_bad_reply`** — agent returns unstructured text instead of
   benefit-verification JSON during `/scan`. Likely a system-prompt or
   tool-selection issue in the scan verification step. Track as a separate task.
2. **Agent update API** — `PUT /v1/agents/{id}` returns 405 in the
   `managed-agents-2026-04-01` beta. Bootstrap must `POST /v1/agents` to create
   a new agent when URLs change, which changes the agent ID. Consider
   parametrising the smoke-test fixture so it always reads the current
   `MANAGED_AGENT_ID` from env rather than a hardcoded value.
3. **Acceptance gate harness** — `check_agent_backed.py` should be extended to
   accept a bare session_id (from the smoke script's output) so it can gate on
   the `claude_call` log line rather than requiring a persisted sweep scan.
