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

## Seed Data

Before scanning works end-to-end, Qdrant must be seeded:
```
cd backend && PYTHONPATH=src python3 -m swiss_legal_api.seeding.seed_qdrant
```

## Running Tests (offline)

```
cd backend && PYTHONPATH=src pytest tests/test_schemas.py tests/test_trigger.py -v
```

## Key Files

- `backend/src/swiss_legal_api/api/main.py` — FastAPI app
- `backend/src/swiss_legal_api/engine/scan.py` — Benefit scan engine
- `backend/src/swiss_legal_api/engine/trigger.py` — Trigger DSL evaluator
- `backend/src/swiss_legal_api/engine/verify.py` — Claude-based verifier
- `backend/seed/entitlements.json` — Entitlement catalog (15 entitlements)
- `backend/seed/law_articles.json` — Swiss law articles for Qdrant
- `frontend/app/page.tsx` — Profile wizard form
- `frontend/app/results/page.tsx` — Results page with benefit cards
- `frontend/lib/api-types.ts` — Auto-generated from backend OpenAPI
- `frontend/lib/api-client.ts` — Typed openapi-fetch client

## Legal Disclaimer

This software is not a substitute for advice from a Swiss attorney registered with a cantonal bar.
