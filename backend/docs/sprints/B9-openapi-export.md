# B9 — OpenAPI Export Script

**Status:** ✅ Complete  
**Tests:** Manual verification (script exits 0, file present, paths correct)

## Purpose
Generate a static `openapi.json` file at repo root so the frontend can consume it via `openapi-typescript` to auto-generate TypeScript types — no live server needed.

## Files Created
| File | Purpose |
|---|---|
| `scripts/export_openapi.py` | Dumps `app.openapi()` to `openapi.json` |

## Script Behaviour
1. Imports `app` from `swiss_legal_api.api.main` (triggers FastAPI schema generation)
2. Calls `app.openapi()` — returns the full OpenAPI 3.1 dict
3. Writes `openapi.json` with `indent=2` to repo root (resolved relative to script location)
4. Prints `Wrote /path/to/openapi.json with 3 paths` and exits 0

## Generated Output
```json
{
  "openapi": "3.1.0",
  "info": {"title": "Swiss Legal Agent API", "version": "0.1.0"},
  "paths": {
    "/health": {...},
    "/scan": {...},
    "/chat": {...}
  }
}
```

## .gitignore
`openapi.json` is already excluded — it is a generated artefact, not source-of-truth.

## Acceptance Criteria — All Met
- Script exits 0 ✅
- `openapi.json` created at repo root ✅
- 3 paths present: `/health`, `/scan`, `/chat` ✅
- Not committed to version control ✅
