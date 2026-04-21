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

## Dropped Articles

The following articles could not be reproduced verbatim from Fedlex English translations
and were excluded from the seed corpus. Entitlements that depend on them were also dropped
or replaced with INFO-only placeholders:

_(This section is updated during Phase B2 seeding.)_

## Law Article Sources

All law text in `seed/law_articles.json` is sourced from:
- **SR 220** (Code of Obligations / CO): https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en
- **SR 642.11** (Direct Federal Tax Act / DBG): https://www.fedlex.admin.ch/eli/cc/1991/1184_1184_1184/en
- **SR 831.40** (Occupational Pensions Act / BVG): https://www.fedlex.admin.ch/eli/cc/1983/797_797_797/en
- **SR 837.0** (Unemployment Insurance Act / AVIG): https://www.fedlex.admin.ch/eli/cc/1982/2184_2184_2184/en

## Legal Disclaimer

This software is not a substitute for advice from a Swiss attorney registered with a cantonal bar.
