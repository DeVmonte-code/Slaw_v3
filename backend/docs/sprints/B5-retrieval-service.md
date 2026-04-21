# B5 — Retrieval Service

**Status:** ✅ Complete  
**Tests:** 1/1 passed (live)

## Purpose
Vector-search Qdrant for the most relevant law article chunks for a given citation, filtered by `sr_number` + `article` to guarantee legal grounding.

## Files Created
| File | Purpose |
|---|---|
| `src/swiss_legal_api/engine/retrieval.py` | `retrieve_for_citation()`, `RetrievedChunk` |
| `tests/test_retrieval.py` | 1 live-gated test |

## Implementation Notes
- Uses `client.query_points(query=vec, ...).points` — **NOT** `client.search()` (removed in qdrant-client 1.17+)
- Filter: `sr_number` + `article` must both match — prevents cross-article hallucination
- Returns up to 3 `RetrievedChunk(text, score)` objects
- Query embedding uses `embed_query()` with `"query: {article} {extra_query}"` prefix

## Critical Fix Applied
`qdrant_client.QdrantClient.search()` was removed in v1.12+. Replaced with:
```python
results = client.query_points(
    collection_name=..., query=vec, limit=3,
    query_filter=..., with_payload=True,
).points
```

## Acceptance Criteria — All Met
- 1/1 live test passes (skipped when `QDRANT_URL` absent) ✅
- mypy + ruff clean ✅
