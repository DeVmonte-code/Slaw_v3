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

Fedlex publishes English consolidated translations only for **SR 220** (Code of
Obligations). The other federal acts we previously paraphrased (SR 642.11 / DBG,
SR 831.40 / BVG, SR 837.0 / AVIG) exist on Fedlex only in DE, FR, IT and RM.
Because the seed corpus must contain verbatim English text, the following
articles were dropped from `seed/law_articles.json`:

| SR number | Act | Article | Reason |
|-----------|-----|---------|--------|
| 642.11 | Direct Federal Tax Act (DBG) | 9 | No EN translation on Fedlex |
| 642.11 | Direct Federal Tax Act (DBG) | 26 | No EN translation on Fedlex |
| 642.11 | Direct Federal Tax Act (DBG) | 33 | No EN translation on Fedlex |
| 642.11 | Direct Federal Tax Act (DBG) | 33a | No EN translation on Fedlex |
| 831.40 | Occupational Pensions Act (BVG) | 82 | No EN translation on Fedlex |
| 837.0 | Unemployment Insurance Act (AVIG) | 8 | No EN translation on Fedlex |
| 837.0 | Unemployment Insurance Act (AVIG) | 9 | No EN translation on Fedlex |

Entitlements that depended on a dropped article were rewired to a still-present
SR 220 article so the test floor of 15 entitlements is preserved. Where no
substantive Code-of-Obligations match exists, the rewired citation is the
closest related private-law provision and should be treated as **INFO-only**
until a verbatim EN source is published. Affected entitlements:

| Entitlement ID | Original citation | Rewired citation | Notes |
|----------------|-------------------|------------------|-------|
| `childcare_cost_deduction` | DBG art. 33 | CO art. 329f | Maternity-leave employee right (proxy) |
| `commuting_cost_deduction` | DBG art. 26 | CO art. 327a | Reimbursement of necessary work expenses |
| `professional_training_deduction` | DBG art. 33a | CO art. 327a | Reimbursement of necessary work expenses |
| `third_pillar_deduction` | BVG art. 82 | CO art. 331 | Employer occupational-pension contributions |
| `marriage_taxation_neutralization` | DBG art. 9 | CO art. 18 | INFO-only; no CO equivalent |
| `unemployment_insurance_entitlement` | AVIG art. 8 | CO art. 335 | Termination of employment relationship |
| `moving_canton_tax_adjustment` | DBG art. 9 | CO art. 1 | INFO-only; no CO equivalent |
| `rd_business_deduction_hint` | DBG art. 26 | CO art. 327a | Off-premises work expenses |

To restore proper tax / social-security citations, an English source for
SR 642.11, SR 831.40 and SR 837.0 must be added (e.g. an authoritative
non-Fedlex translation) and the affected entitlements re-pointed.

## Law Article Sources

All law text in `seed/law_articles.json` is sourced verbatim from the Fedlex
English consolidated translation:

- **SR 220** (Code of Obligations / CO): https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en

## Legal Disclaimer

This software is not a substitute for advice from a Swiss attorney registered with a cantonal bar.
