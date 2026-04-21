# B10 — End-to-End Backend Smoke

**Status:** ✅ Complete  
**Result:** `=== Backend smoke PASSED ===`

## Purpose
A single shell script that validates the entire backend stack in one command: lint → types → unit tests → live API smoke — producing a green/red signal for CI readiness.

## Files Created
| File | Purpose |
|---|---|
| `scripts/smoke.sh` | Full end-to-end smoke test script |

## Script Stages
| Stage | Command | Passes When |
|---|---|---|
| Lint + types | `ruff check src tests && mypy src` | Exit 0, 20 source files clean |
| Offline unit tests | `pytest tests/test_schemas.py tests/test_seed.py tests/test_trigger.py -v` | 12/12 pass |
| Start API | `uvicorn ... & sleep 4` | Process alive |
| Health check | `curl -sf /health` | `{"ok":true}` |
| OpenAPI paths | `curl -sf /openapi.json \| python -c ...` | `['/health', '/scan', '/chat']` |
| Live scan | `curl -sf POST /scan -d @fixtures/luis_profile.json` | ≥5 benefits, 2 required IDs |
| Export OpenAPI | `python scripts/export_openapi.py` | Exit 0, file written |
| Final check | `echo === Backend smoke PASSED ===` | Reached ✅ |

## Implementation Notes
- `set -euo pipefail` — any failure aborts the script with non-zero exit
- `trap "kill $SERVER_PID 2>/dev/null || true" EXIT` — ensures uvicorn is killed even on failure
- Live scan `--max-time 180` accommodates cold LLM response times
- Server startup used a polling loop (`curl -sf ... && break`) to avoid race conditions

## Offline Tests Summary (12/12)
| File | Tests | Result |
|---|---|---|
| `test_schemas.py` | 5 | ✅ PASSED |
| `test_seed.py` | 3 | ✅ PASSED |
| `test_trigger.py` | 4 | ✅ PASSED |

## Live Scan Output
```
Benefits returned: 10
required IDs present
```

## Acceptance Criteria — All Met
- Script exits 0 ✅
- Final line: `=== Backend smoke PASSED ===` ✅
- `openapi.json` written and ready for frontend ✅
- `rent_reduction_reference_rate` in results ✅
- `childcare_cost_deduction` in results ✅
