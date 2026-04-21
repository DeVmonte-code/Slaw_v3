# B7 — Scan Orchestrator

**Status:** ✅ Complete  
**Tests:** 1/1 live test passed (~35s)

## Purpose
Orchestrate the full benefit scan: evaluate all 15 entitlement triggers, fan-out to `verify_entitlement()` for those that match, and return a ranked `BenefitReport`.

## Files Created
| File | Purpose |
|---|---|
| `src/swiss_legal_api/catalog.py` | `load_catalog()` with `@lru_cache(maxsize=1)` |
| `src/swiss_legal_api/engine/scan.py` | `run_benefit_scan()` |
| `tests/test_scan.py` | 1 live-gated integration test |
| `fixtures/luis_profile.json` | ZH tenant + employee + parent, 2 children, childcare CHF 18,000/yr |

## run_benefit_scan() Algorithm
1. Load catalog (cached) — 15 entitlements
2. For each entitlement, call `evaluate_trigger(entitlement.trigger, profile)` synchronously
3. Collect `matched` entries (trigger matched) with their `evidence` lists
4. Fan-out: concurrently call `verify_entitlement()` for all matched entries, gated by `asyncio.Semaphore(settings.scan_concurrency)` (default 3)
5. Filter: keep only results where `verify_result.confidence >= entitlement.confidence_floor`
6. Rank: descending by `confidence × log1p(max EstimatedValue)` (CHF)
7. Return `BenefitReport(profile_id, benefits, generated_at)`

## luis_profile.json Summary
```json
{
  "canton": "ZH", "age": 34, "employment_status": "employed",
  "children_count": 2, "annual_income_chf": 95000,
  "monthly_rent_chf": 2800, "childcare_cost_chf_annual": 18000,
  "life_events": [{"event": "new_job", "date": "2024-01-15"}]
}
```

## Acceptance Criteria — All Met
- ≥5 benefits returned ✅
- `rent_reduction_reference_rate` present ✅
- `childcare_cost_deduction` present ✅
- Test runtime ~35s (3 concurrent LLM calls) ✅
