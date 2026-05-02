# swiss-legal-api

Proactive Rights Discovery API for Swiss residents.

## Overview

The API accepts a `ContextProfile` (canton, employment, housing, household, income, life events)
and runs a **Benefit Scan**: deterministic trigger evaluation against an `EntitlementCatalog`,
followed by Claude-verified retrieval from a Qdrant vector store seeded with Swiss federal law.

## Requirements

- Python 3.12
- [uv](https://github.com/astral-sh/uv) package manager
- Qdrant Cloud free-tier cluster
- Anthropic API key

## Setup

```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install dependencies
uv python install 3.12
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Copy and populate secrets
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY, QDRANT_URL, QDRANT_API_KEY

# Seed Qdrant
python -m swiss_legal_api.seeding.seed_qdrant

# Start the API
uvicorn swiss_legal_api.api.main:app --host 0.0.0.0 --port 8000
```

Swagger UI: http://localhost:8000/docs

## End-to-End Test

```bash
curl -X POST http://localhost:8000/scan \
  -H "content-type: application/json" \
  -d @fixtures/luis_profile.json
```

## Health Endpoints

| Path      | Purpose                                             |
| --------- | --------------------------------------------------- |
| `/health` | Cheap liveness — proves the process is up.          |
| `/readyz` | Deep readiness — pings Qdrant; 503 if unreachable.  |

`/readyz` is what a load balancer should poll. `/health` is for the process supervisor.

## Configuration

All settings are read from the environment (see `.env.example`).

| Variable               | Default                                | Notes                                                                                          |
| ---------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`    | (empty)                                | Required for live `/scan` and `/chat`.                                                         |
| `CLAUDE_MODEL`         | `claude-opus-4-7`                      | Override per environment if needed.                                                            |
| `QDRANT_URL`           | (empty)                                | Required at startup (lifespan pings it).                                                       |
| `QDRANT_API_KEY`       | (empty)                                | Required for Qdrant Cloud.                                                                     |
| `QDRANT_COLLECTION`    | `swiss_law`                            |                                                                                                |
| `EMBEDDING_MODEL`      | `intfloat/multilingual-e5-small`       | Pre-warmed at startup.                                                                         |
| `SCAN_CONCURRENCY`     | `3`                                    | Anthropic semaphore.                                                                           |
| `LOG_LEVEL`            | `INFO`                                 | `DEBUG` / `INFO` / `WARNING` / `ERROR`.                                                        |
| `FRONTEND_ORIGIN`      | (empty)                                | Single CORS origin to allow. Mutually exclusive with `CORS_ALLOW_ORIGINS`.                     |
| `CORS_ALLOW_ORIGINS`   | (empty)                                | Comma-separated CORS origins. Wins over `FRONTEND_ORIGIN` if both set.                         |
| `APP_ENV`              | `development`                          | Set to `production` (or `prod`) to make CORS origins mandatory — startup fails if neither origin var is set. |

### CORS

If neither `FRONTEND_ORIGIN` nor `CORS_ALLOW_ORIGINS` is set in development
(`APP_ENV=development`, the default), the API falls back to `allow_origins=["*"]` and
emits a single `WARNING` log line at startup. In production (`APP_ENV=production`),
the same misconfiguration **refuses to start** — startup raises `RuntimeError` rather
than silently fail open.

```bash
# Single origin (most common)
export FRONTEND_ORIGIN=https://app.example.ch

# Multiple origins (e.g. staging + production)
export CORS_ALLOW_ORIGINS=https://app.example.ch,https://staging.example.ch
```

## Logging

Structured single-line JSON-ish logs go to stdout (timestamp, level, logger, message).
Notable log lines emitted by the engine:

- `scan_complete profile_hash=… triggered=N verified=M suppressed=K duration_ms=…`
- `claude_verify entitlement_id=… latency_ms=… input_tokens=… output_tokens=…`
- `verify_entitlement failed for entitlement_id=… exc_type=…` (was previously silent)

500 responses on `/scan` and `/chat` always log the full exception server-side and return
only `{"detail": "Internal error"}` to the client — never `str(exc)` (which can leak
Anthropic API keys, request bodies, etc.).

## Source Languages

Fedlex publishes a downloadable English consolidated text for **SR 220** (Code of
Obligations) only. The other three laws referenced by the seed corpus are not available
in English, only in DE / FR / IT. Per the v3 spec's "no paraphrased law text" rule, the
seed therefore mixes verbatim **EN** for SR 220 and verbatim **DE** for the other three:

| SR        | Title                                               | Source language used | Articles in seed                                       | Fedlex URL                                                                  |
| --------- | --------------------------------------------------- | -------------------- | ------------------------------------------------------ | --------------------------------------------------------------------------- |
| `220`     | Code of Obligations (OR / CO)                       | EN                   | 1, 18, 24, 28, 41, 42, 43, 62, 63, 197, 257e, 270a, 271, 321c, 327a, 328, 329f, 331, 335, 335c | https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en                        |
| `642.11`  | Direct Federal Tax Act (DBG / LIFD)                 | DE                   | 9, 26, 27, 33 Abs 1, 33 Abs 3, 35, 36 Abs 2, 212        | https://www.fedlex.admin.ch/eli/cc/1991/1184_1184_1184/de                   |
| `831.40`  | Occupational Pensions Act (BVG / LPP)               | DE                   | 1                                                       | https://www.fedlex.admin.ch/eli/cc/1983/797_797_797/de                      |
| `837.0`   | Unemployment Insurance Act (AVIG / LACI)            | DE                   | 8                                                       | https://www.fedlex.admin.ch/eli/cc/1982/2184_2184_2184/de                   |

Each entry in `seed/law_articles.json` declares its source language in its `language`
field, and each `quote_under_15_words` slice in `seed/entitlements.json` is a literal
copy from the corresponding article in the same language. The verification prompt
(`engine/verify.py`) explicitly states that retrieved DE text is treated as authoritative
alongside EN — Claude reasons natively in both languages.

### Verification

Before relying on this corpus for any production legal advice, spot-check each `text`
field against the Fedlex URL above for its `sr_number`. The DE entries were captured
from Fedlex consolidated text but Fedlex amends the consolidated versions when the laws
are revised, so the seed should be re-checked at every release cut.

### Dropped Articles

None. Every entitlement in `seed/entitlements.json` resolves to an article in
`seed/law_articles.json` after the EN+DE rewrite. If a future spec change requires an
article that has no Fedlex EN translation **and** is not reproducible verbatim in DE,
list it here with the reason and remove the dependent entitlement.

## Trigger DSL

The trigger DSL (`schemas/trigger_dsl.py`) is a Pydantic v2 tagged union dispatched
through a callable `Discriminator`. Each variant carries a `kind: Literal[…]` field for
OpenAPI clarity. Existing JSON like `{"eq": [...]}` parses unchanged — the discriminator
infers the tag from the operator key when `kind` is missing — so seed and fixture data
do not need migration. All variants set `extra="forbid"` so payloads that smuggle two
operators in one node (e.g. `{"eq": [...], "gt": [...]}`) fail loudly instead of
silently dropping the unmatched branch.

## Legal Disclaimer

This software is not a substitute for advice from a Swiss attorney registered with a cantonal bar.
