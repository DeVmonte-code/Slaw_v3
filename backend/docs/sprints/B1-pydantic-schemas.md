# B1 — Pydantic Schemas

**Status:** ✅ Complete  
**Tests:** 5/5 passed

## Purpose
Define every Pydantic v2 data model used across the full stack: citations, context profiles, the trigger DSL, entitlement catalog entries, and benefit reports.

## Files Created
| File | Key Types |
|---|---|
| `src/swiss_legal_api/__init__.py` | (empty package marker) |
| `src/swiss_legal_api/schemas/__init__.py` | Re-exports 9 public types |
| `src/swiss_legal_api/schemas/citation.py` | `Citation` — SR number regex + ≤15-word quote validator |
| `src/swiss_legal_api/schemas/context_profile.py` | `ContextProfile`, `LifeEvent`, 7 Literal type aliases |
| `src/swiss_legal_api/schemas/trigger_dsl.py` | `TriggerExpr` union of 11 node types; `model_rebuild()` for forward refs |
| `src/swiss_legal_api/schemas/entitlement.py` | `Entitlement`, `TitleI18n`, `EstimatedValue` |
| `src/swiss_legal_api/schemas/benefit_report.py` | `Benefit`, `BenefitReport`, `EvidenceItem` |
| `tests/__init__.py` | (empty) |
| `tests/test_schemas.py` | 5 unit tests |

## Key Design Notes
- `TriggerExpr` is a `typing.Union` of all DSL node models — Pydantic v2 discriminated union via field names
- `All` and `Any_` are self-referential; `model_rebuild()` called after all types are defined
- `Not` uses `alias="not"` with `populate_by_name=True` to avoid Python keyword clash
- `In` uses `alias="in"` for the same reason
- `citation.sr_number` validated against `^\d+(\.\d+)?$`
- `quote_under_15_words` validated at ≤15 space-separated tokens

## Acceptance Criteria — All Met
- 5/5 tests pass ✅
- `ruff check` clean ✅
- `mypy` clean ✅
