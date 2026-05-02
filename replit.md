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
