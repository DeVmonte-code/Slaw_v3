# B4 — Trigger Evaluator

**Status:** ✅ Complete  
**Tests:** 4/4 passed

## Purpose
Pure-Python DSL evaluator that determines, for a given `ContextProfile`, whether an `Entitlement`'s trigger expression matches — and records the specific field evidence that caused the match.

## Files Created
| File | Purpose |
|---|---|
| `src/swiss_legal_api/engine/__init__.py` | (empty) |
| `src/swiss_legal_api/engine/trigger.py` | `EvalResult`, `evaluate_trigger()` |
| `tests/test_trigger.py` | 4 unit tests |

## DSL Node Types Handled
| Node | Semantics |
|---|---|
| `All` | Short-circuits on first false; accumulates all evidence |
| `Any_` | Passes if any sub-expr matches |
| `Not` | Inverts result, passes evidence through |
| `Eq` | `field == value` |
| `Gte` / `Lte` / `Gt` / `Lt` | Numeric comparisons |
| `In` | `field in [list]` |
| `Between` | `lo <= field <= hi` |
| `Exists` | Field is not None |
| `EventWithinYears` | ≥1 `LifeEvent` with matching `.event` within last N years |

## Key Design Notes
- `_resolve(profile, path)` walks dotted paths (e.g. `children_count`) through both dict and object attributes
- `_record()` normalises values to `str | int | float | bool | None` for `EvidenceItem` serialisation
- No I/O — pure synchronous Python, no Anthropic/Qdrant imports
- `evaluate_trigger` returns `EvalResult(matched, evidence)` — evidence fed directly into `Benefit.evidence`

## Acceptance Criteria — All Met
- 4/4 tests pass ✅
- mypy clean ✅
- ruff clean ✅
