# B3 — Qdrant Seeder

**Status:** ✅ Complete  
**Result:** Seeded 21 articles into `swiss_law`

## Purpose
Embed and upsert all law articles into Qdrant Cloud so the retrieval service can vector-search them at scan time.

## Files Created
| File | Purpose |
|---|---|
| `src/swiss_legal_api/config.py` | `Settings(BaseSettings)` — reads secrets from `.env`; singleton `settings` instance |
| `src/swiss_legal_api/seeding/__init__.py` | (empty) |
| `src/swiss_legal_api/seeding/embedder.py` | `get_embedder()` (lru_cache), `embed_passage()`, `embed_query()` |
| `src/swiss_legal_api/seeding/seed_qdrant.py` | One-shot seeder script |

## Embedding Model
- **Model:** `intfloat/multilingual-e5-small`
- **Dimensions:** 384
- **Distance:** COSINE
- **Prefixes:** `"passage: "` for corpus text, `"query: "` for search queries (E5 convention)
- Cached locally via `SentenceTransformer` + `lru_cache(maxsize=1)`

## Seeder Behaviour
1. Reads `seed/law_articles.json`
2. Creates Qdrant collection `swiss_law` (384-dim COSINE) if absent
3. Creates KEYWORD payload indices on `sr_number`, `article`, `language`
4. Embeds each article text with `embed_passage()` and upserts as `PointStruct`
5. Idempotent via `upsert(wait=True)` — safe to re-run

## Settings (config.py)
| Variable | Default | Source |
|---|---|---|
| `anthropic_api_key` | `""` | `.env` |
| `claude_model` | `claude-opus-4-7` | `.env` |
| `qdrant_url` | `""` | `.env` |
| `qdrant_api_key` | `""` | `.env` |
| `qdrant_collection` | `swiss_law` | `.env` |
| `embedding_model` | `intfloat/multilingual-e5-small` | `.env` |
| `scan_concurrency` | `3` | `.env` |

## Acceptance Criteria — All Met
- Script exits 0 ✅
- Prints `Seeded 21 articles into swiss_law` ✅
- mypy + ruff clean ✅
