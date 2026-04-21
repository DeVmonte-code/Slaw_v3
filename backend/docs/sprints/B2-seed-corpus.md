# B2 — Seed Corpus

**Status:** ✅ Complete  
**Tests:** 3/3 passed

## Purpose
Provide the verbatim legal text corpus (Swiss federal law articles) and the curated entitlement catalog that the scan engine reasons over.

## Files Created
| File | Content |
|---|---|
| `seed/law_articles.json` | 21 articles from CO, DBG, BVG, AVIG |
| `seed/entitlements.json` | Exactly 15 entitlements |
| `tests/test_seed.py` | 3 data-integrity tests |

## Corpus Coverage (law_articles.json)
| Code | SR | Articles |
|---|---|---|
| CO (Code of Obligations) | 220 | 1, 18, 24, 28, 41, 42, 43, 62, 63, 257e, 270a, 321c, 328, 335c |
| DBG (Federal Tax Act) | 642.11 | 9, 26, 33, 33a |
| BVG (Occupational Pension) | 831.40 | 82 |
| AVIG (Unemployment Insurance) | 837.0 | 8, 9 |

## Entitlement IDs
`rent_reduction_reference_rate`, `rent_deposit_interest`, `employer_health_protection`, `overtime_compensation`, `notice_period_seniority`, `childcare_cost_deduction`, `commuting_cost_deduction`, `professional_training_deduction`, `third_pillar_deduction`, `marriage_taxation_neutralization`, `unemployment_insurance_entitlement`, `moving_canton_tax_adjustment`, `fundamental_error_rescission`, `rd_business_deduction_hint`, `tort_claim_placeholder`

## Key Design Notes
- Every entitlement's `source_citations` must reference a `(sr_number, article)` pair present in `law_articles.json` — enforced by `test_entitlement_citations_exist_in_corpus`
- `fundamental_error_rescission` and `tort_claim_placeholder` use `{"all":[]}` trigger (always fires) with `confidence_floor: 0.5` — purely informational
- No cantonal statutes added (deferred)

## Acceptance Criteria — All Met
- 3/3 seed tests pass ✅
- `law_articles.json` has 21 rows (≥20) ✅
- `entitlements.json` has exactly 15 rows ✅
- All citations resolve to corpus articles ✅
