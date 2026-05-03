# Swiss Legal Rights Scan (Slaw)

A Proactive Rights Discovery service for Swiss residents.

## Architecture

- **Backend** (`backend/`): Python 3.12 FastAPI API
  - Port: 8000 (localhost only)
  - Entry: `PYTHONPATH=src uvicorn swiss_legal_api.api.main:app --host localhost --port 8000`
  - Endpoints: `GET /health`, `POST /scan`, `POST /chat`
  - Dependencies: FastAPI, Pydantic v2, Anthropic SDK, Qdrant client, sentence-transformers

- **Frontend** (`frontend/`): Next.js 15 + TypeScript + Tailwind CSS
  - Port: 5000 (0.0.0.0 for Replit preview)
  - Entry: `pnpm start` (production) or `pnpm dev` (development)
  - Pages: `/` (profile wizard form), `/results` (benefit cards)
  - Types auto-generated from backend OpenAPI schema

## How It Works

1. User fills in a `ContextProfile` (canton, employment, housing, household, income)
2. Frontend POSTs to `/scan` on the backend
3. Backend evaluates deterministic triggers against the EntitlementCatalog
4. For each triggered entitlement, Claude verifies via Qdrant-retrieved Swiss law text
5. Returns a ranked `BenefitReport` with citations, confidence, evidence, and required actions

## Required Secrets

- `ANTHROPIC_API_KEY` — for Claude verification and chat
- `QDRANT_URL` — Qdrant Cloud cluster URL
- `QDRANT_API_KEY` — Qdrant Cloud API key

## Optional Config

- `CLAUDE_MODEL` (default: `claude-opus-4-7`)
- `QDRANT_COLLECTION` (default: `swiss_law`)
- `EMBEDDING_MODEL` (default: `intfloat/multilingual-e5-small`)
- `SCAN_CONCURRENCY` (default: `3`)
- `SCORE_THRESHOLD` (default: `0.55`) — Qdrant cosine floor; chunks below are dropped before the verifier and `supports=false` is returned without a Claude call
- `LOG_LEVEL` (default: `INFO`) — JSON-format logs to stdout
- `FRONTEND_ORIGIN` / `CORS_ALLOW_ORIGINS` — CORS origins; defaults to `*` in dev with WARNING
- `APP_ENV` (default: `development`) — set to `production` to make CORS origins mandatory at startup

## Anti-hallucination guardrails (Task #18)

Each Qdrant chunk and `Citation` carries `canton`, `effective_date`, and
`repealed_date`. Retrieval filters on:
- `canton ∈ {profile.canton, "CH"}` (federal law applies in every canton)
- `effective_date <= today` (no not-yet-in-force law)
- `repealed_date IS NULL OR > today` (no repealed law)
- cosine similarity `>= SCORE_THRESHOLD` (refuse-on-empty, no Claude call)

The verifier marks DE/FR/IT chunks as `is_authoritative=true` and EN as a
courtesy-translation aid (graceful fallback to EN when no original-language
chunk is in the corpus). The `Benefit` returned by `/scan` surfaces the top
chunk's `effective_date` and `score` on `best_citation`.

## Observability

- `GET /readyz` — deep health (pings Qdrant; returns 503 on failure)
- `GET /health` — liveness only
- Structured JSON logs include `scan_complete` (profile_hash, triggered/verified/suppressed counts, duration_ms) and `claude_verify` (entitlement_id, latency_ms, token usage)
- 500 responses always return `{"detail": "Internal error"}` — full exception logged server-side

## Seed Data


**Note:** The authoritative source for Federal law is now `backend/seed/law_articles.fedlex.json`. The manual `law_articles.json` is strictly for fallback. Orphaned SR 831.40 articles were pruned.
Before scanning works end-to-end, Qdrant must be seeded:
```
cd backend && PYTHONPATH=src python3 -m swiss_legal_api.seeding.seed_qdrant
```

## Running Tests (offline)

```
cd backend && python -m pytest tests/ -v
```

Live-secrets-gated tests in `test_api.py::test_scan_endpoint_live`,
`test_scan.py`, and `test_retrieval.py` self-skip when `ANTHROPIC_API_KEY` /
`QDRANT_URL` are not the real production values. The other 23 tests run
offline using respx + monkeypatched Qdrant retrieval.

## Scheduled benefit sweep (Task #22)

Stateful layer added on top of the synchronous `/scan` endpoint:
SQLite-backed `users` / `scan_results` / `alerts` tables, an
APScheduler nightly job (off by default, gated on `SWEEP_ENABLED=1`),
and a Fedlex-diff sub-job that force-classifies `UPDATED` alerts when
a user's cited articles change in `seed/law_articles.fedlex.json`.

Key modules:
- `backend/src/swiss_legal_api/storage.py` — sqlite3 persistence (users, scans, alerts; WAL mode; idempotent upserts)
- `backend/src/swiss_legal_api/engine/sweep.py` — `classify_diff` (NEW/GONE/UPDATED), `fedlex_changed_articles`, `sweep_all_users`
- `backend/src/swiss_legal_api/scheduler.py` — APScheduler glue, started in FastAPI lifespan when enabled
- `backend/src/swiss_legal_api/schemas/sweep.py` — `UserRecord`, `Alert`, `AlertPayload`
- `backend/tests/test_sweep.py` — 23 offline tests (classifier, Fedlex diff, storage, orchestrator, HTTP endpoints)
- `frontend/app/alerts/page.tsx` — Alerts inbox UI
- `frontend/lib/api-client.ts` — `getOrCreateUserId()` localStorage helper
- See `backend/README.md` "Scheduled sweep" section for full configuration / endpoint reference.

## Managed Agents pipeline (Task #26 / #37)

Every `_call_claude` site (`engine/verify.py`, `api/chat.py`) and the
batched scan driver (`engine/scan.py::_verify_via_managed_session`)
route through a Claude Managed Agents session instead of
`messages.create`. **Default is now ON** (`USE_MANAGED_AGENTS=1`) — set
`USE_MANAGED_AGENTS=0` only for local dev / CI / unit tests where no
real agent is provisioned. The offline test suite pins this in
`backend/tests/conftest.py` so existing tests keep using the local
verifier path.

- `backend/src/swiss_legal_api/mcp_servers/{swiss_law,contract_tools,user_context}.py`
  — three MCP servers (read-only retrieval; verify/scan; user docs).
  Each tool is a thin wrapper around shared callables; the SSOT test
  asserts identity so Config A and Config B can't drift.
- `backend/src/swiss_legal_api/engine/agent_runner.py` — opens the SSE
  stream first, sends `user.message`, consumes events until
  `session.status_idle`, returns `(text, AgentProvenance)` with
  `call_kind="sessions.events"` populated. `agent_backed` is True iff
  ≥1 tool/MCP-tool event was observed.
- `backend/src/swiss_legal_api/managed_agents/bootstrap.py` —
  `python -m swiss_legal_api.managed_agents.bootstrap` provisions agent
  + environment + vault. Defaults to writing IDs to `backend/.env`;
  pass `--no-write-env --out /tmp/managed-ids.json` for the prod
  flow that registers the IDs as Replit Secrets / shared env vars.
- Operator runbook: `backend/doc/managed-agents-setup.md` (this is the
  one to follow for new deployments — covers `MCP_BASE_URL` derivation,
  the bootstrap CLI flags, and the smoke command).
- `backend/scripts/managed_agents_smoke.py` — opens one real session
  and exits non-zero with a precise reason (config missing / no MCP
  tool used / fatal session error) so a misconfigured deploy is
  caught before flipping `USE_MANAGED_AGENTS`.
- Tests: `backend/tests/test_agent_runner.py` (mocked SSE),
  `backend/tests/test_mcp_single_source_of_truth.py`.

Required settings (validated at startup — Task #37): `MANAGED_AGENT_ID`,
`MANAGED_ENVIRONMENT_ID`, `MANAGED_VAULT_ID`, `MANAGED_AGENT_VERSION`,
plus either `MCP_BASE_URL` (recommended — derives the three per-server
URLs from the deployment host) or each of `MCP_SWISS_LAW_URL`,
`MCP_CONTRACT_TOOLS_URL`, `MCP_USER_CONTEXT_URL`. The FastAPI
`lifespan` runs `_validate_managed_agents_config()` and raises
`RuntimeError` with the missing variable list before serving any
requests, so a misconfigured deploy crashes on boot instead of silently
serving zero-result scans. `GET /readyz` additionally probes each MCP
URL (concurrent HTTPS GET, ≤4 s timeout) and returns 503 with the
per-server status (`reachable` / `unreachable` / `timeout` / `server_error`)
when any server is down. Hit `/readyz?include=mcp` to force the probe
even when `USE_MANAGED_AGENTS=0`.

## How a scan runs (Task #37)

1. Frontend `POST /scan/stream` with the user's profile.
2. Backend evaluates deterministic triggers from `seed/entitlements.json`
   and emits a `triggered` SSE event with the count.
3. `_verify_via_managed_session` opens **one** managed-agents session
   for the whole batch and streams its events. Every
   `agent.mcp_tool_use` is forwarded through the SSE channel as a
   `tool_call` event (`{tool, server, label}`); the frontend renders
   the latest 5 in a live feed inside `ScanInProgress`. **Note:**
   `agent.message` events are intentionally NOT forwarded — the
   verbatim model output is the JSON the parser owns, and surfacing
   intermediate planning tokens to the UI would be both noisy and a
   small leak surface (no PII redaction has been performed on it).
4. The agent's batched JSON reply is parsed back into one
   `VerifyResult` per entitlement; unresolved citations and zero-MCP
   sessions are suppressed with `requires_evidence_review`.
5. The final `BenefitReport` ships in a `complete` SSE event and is
   cached in `sessionStorage`. The plain `POST /scan` path remains as
   the fallback when SSE is unavailable.

## Key Files

- `backend/src/swiss_legal_api/api/main.py` — FastAPI app
- `backend/src/swiss_legal_api/engine/scan.py` — Benefit scan engine
- `backend/src/swiss_legal_api/engine/trigger.py` — Trigger DSL evaluator
- `backend/src/swiss_legal_api/engine/verify.py` — Claude-based verifier
- `backend/seed/entitlements.json` — Entitlement catalog (15 entitlements)
- `backend/seed/law_articles.json` — Swiss law articles for Qdrant (verbatim EN for SR 220, verbatim DE for SR 642.11 / 831.40 / 837.0). Each entry carries `canton`, `effective_date`, and `repealed_date` for the retrieval guardrails.
- `backend/tests/test_verify_guardrails.py` — Filter-construction + verifier short-circuit tests for Task #18
- `backend/tests/test_scan_mocked.py` — End-to-end scan test using respx + monkeypatched retrieval (runs offline)
- `backend/tests/conftest.py` — Test env defaults (placeholder ANTHROPIC_API_KEY for offline mocked tests)
- `frontend/app/page.tsx` — Profile wizard form
- `frontend/app/results/page.tsx` — Results page with benefit cards
- `frontend/lib/api-types.ts` — Auto-generated from backend OpenAPI
- `frontend/lib/api-client.ts` — Typed openapi-fetch client
- `frontend/Dockerfile` — Production container build (3-stage node:20-alpine, port 5000)
- `frontend/.dockerignore` — Build context exclusions
- `frontend/scripts/smoke.sh` — End-to-end frontend smoke test (run with workflow stopped)

## Legal Disclaimer

This software is not a substitute for advice from a Swiss attorney registered with a cantonal bar.
