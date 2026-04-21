# B8 — FastAPI App

**Status:** ✅ Complete  
**Tests:** 3/3 passed (2 offline + 1 live, ~32s)

## Purpose
Expose the scan engine and a follow-up Q&A capability as a JSON HTTP API using FastAPI.

## Files Created
| File | Purpose |
|---|---|
| `src/swiss_legal_api/api/__init__.py` | (empty) |
| `src/swiss_legal_api/api/main.py` | FastAPI app, all routes, CORS middleware |
| `src/swiss_legal_api/api/chat.py` | `answer_follow_up()` — retrieves context, calls Claude |
| `tests/test_api.py` | 3 tests (httpx ASGITransport) |

## Endpoints
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | None | Liveness probe → `{"ok": true}` |
| POST | `/scan` | None | Accepts `ContextProfile`, returns `BenefitReport` |
| POST | `/chat` | None | Accepts `ChatRequest`, returns `ChatResponse` |
| GET | `/openapi.json` | None | FastAPI auto-generated schema |
| GET | `/docs` | None | Swagger UI |

## CORS Configuration
```python
allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
```
(broadened for development; restrict in production)

## chat.py Flow
1. If `benefit_id` provided, look up entitlement in catalog
2. Retrieve 3 relevant article chunks via `retrieve_for_citation()`
3. Compose user message with entitlement context prepended
4. Call `AsyncAnthropic.messages.create()`, `max_tokens=800`
5. Return concatenated text blocks

## Testing Approach
- `httpx.AsyncClient(transport=ASGITransport(app=app))` — no server needed for offline tests
- Live scan test gated on `ANTHROPIC_API_KEY` + `QDRANT_URL` env vars
- Timeout 180s for live scan

## Acceptance Criteria — All Met
- `test_health` PASSED ✅
- `test_openapi_schema_available` PASSED ✅
- `test_scan_endpoint_live` PASSED (~32s) ✅
- `curl /health` → `{"ok":true}` ✅
- `/openapi.json` lists `/scan` and `/chat` ✅
