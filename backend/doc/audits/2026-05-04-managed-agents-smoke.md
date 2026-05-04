# Managed-Agents Smoke Audit — 2026-05-04

## Status: GREEN ✓

## Objective

Verify the Managed Agent runtime path end-to-end: smoke-test MCP connectivity,
trigger a live `/scan`, confirm agent-backed provenance on every benefit, and
pass the acceptance gate (`check_agent_backed.py` exit 0, ≥5 benefits at 100%
agent-backed).

---

## Smoke Test — PASS

| Field | Value |
|---|---|
| Script | `backend/scripts/managed_agents_smoke.py` |
| Exit | **0** |
| Session | `sesn_011CahKRocMvYZyD6g9w3UVP` |
| `mcp_tool_use_count` | 4 |
| `agent_backed` | `True` |
| `text_len` | 1605 chars |
| Model | `claude-sonnet-4-6` |
| MCP servers invoked | `swiss-contract-tools-mcp`, `swiss-law-retrieval-mcp` |

- Session created: `POST /v1/sessions` → 200
- Events stream opened: `GET /v1/sessions/{id}/events/stream` → 200
- Qdrant vector search confirmed live for each tool call
- Script exit code: **0**

---

## Live `/scan` Run — PASS

| Field | Value |
|---|---|
| User-Id | `luis-gate-001` |
| `generated_at` | `2026-05-04T10:04:36.633259Z` |
| Outer session | `sesn_011CahKkrivYvwSpX3XzfD2V` |
| `triggered` | 12 |
| `verified` | 10 |
| `suppressed` | 2 (no chunks above threshold) |
| `duration_ms` | ~204,000 ms |
| `agent_backed` | **10 / 10 (100%)** |
| `call_kind` | `sessions.events` for all 10 |

```
scan_complete profile_hash=88a6e006943e047a triggered=12 verified=10
             suppressed=2 duration_ms=204623
managed_scan_session entitlements=12 session=sesn_011CahKkrivYvwSpX3XzfD2V
                     agent_backed=true mcp_tools=12
```

Qdrant queries confirmed live for each `verify_entitlement` MCP tool call
(`swiss_law` collection, real embeddings).

---

## Acceptance Gate — PASS (exit 0)

```
Job: 2026-05-04T10:04:36.633259Z
total_benefits     = 10
agent_backed_pct   = 100.0%
by_call_kind       = {'sessions.events': 10}
by_model           = {'claude-sonnet-4-6': 10}
SUCCESS: acceptance gate passed — 100% of verifications are agent-backed.
GATE_EXIT=0
```

Endpoint: `GET /admin/audits/agent-backed?job_id=2026-05-04T10%3A04%3A36.633259Z`

---

## Bugs Fixed During This Task

| # | Description | Files changed |
|---|---|---|
| 1 | Stream URL `/stream` → `/events/stream` | `agent_runner.py` |
| 2 | Duplicate `StreamableHTTPSessionManager` in lifespan | `main.py` |
| 3 | Replit proxy strips trailing slashes — added `/mcp/:path*` proxy rule, slash-normalizer ASGI middleware, no-slash URL defaults | `next.config.mjs`, `main.py`, `config.py` |
| 4 | `_ingest_event` parsed `event.get("requires_action")` but API sends `stop_reason: {type:"requires_action", event_ids:[…]}` | `agent_runner.py` |
| 5 | Tool confirmation used `decision:"allow"` — API requires `result:"allow"` | `agent_runner.py` |
| 6 | `_build_agent_brief` prompt referenced wrong key; `_resolve_agent_citation` only accepted `citation` | `scan.py` |
| 7 | **Nested managed sessions** — `_verify_local` called `_call_claude` which re-entered the managed-agent path, spawning one full session per entitlement (57 s each × 12 = 684 s). Fixed by extracting `_call_messages_create` and routing `_verify_local` through it directly | `verify.py` |
| 8 | `/scan` endpoint did not persist to `sweep.db` — acceptance gate always saw 0 rows | `main.py` |
| 9 | FK violation on `insert_scan` — `users` row must exist before `scan_results` insert | `main.py` |
| 10 | `managed_session_timeout_s` 180 s too short; raised to 600 s | `config.py` |

---

## Correct Session Topology

```
/scan
  └── _verify_via_managed_session()        ← ONE managed session (outer)
        └── verify_entitlement ×12 (MCP)  ← confirmed, then executes
              └── _verify_local()           ← in-process
                    └── _call_messages_create()  ← direct messages.create (~4 s)
```

One outer managed session per scan orchestrates all 12 `verify_entitlement`
tool calls. Each tool call executes `_verify_local → _call_messages_create`
(direct `messages.create`, ~4 s each). No nested managed sessions.

---

## Infrastructure State After Task #51

| Item | Value |
|---|---|
| `MANAGED_AGENT_ID` | `agent_011CahFzDgdkKuHmxpKAHqop` (version 1) |
| `MANAGED_ENVIRONMENT_ID` | `env_0137NKCALxA8uttrfn7hJJ9B` |
| `MANAGED_VAULT_ID` | `vlt_011CahDumG4DjWqJ8SZbtSEN` |
| MCP URLs | No trailing slash (e.g. `.../mcp/swiss-law`) |
| Next.js proxy routes | `/mcp/:path*` added and built |
| FastAPI middleware | `_mcp_slash_normalizer` added |
| `managed_session_timeout_s` | 600 s |
| Anthropic beta header | `managed-agents-2026-04-01` |
