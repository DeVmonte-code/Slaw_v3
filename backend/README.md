# swiss-legal-api

Proactive Rights Discovery API for Swiss residents.

## Overview

The API accepts a `ContextProfile` (canton, employment, housing, household, income, life events)
and runs a **Benefit Scan**: deterministic trigger evaluation against an `EntitlementCatalog`,
followed by Claude-verified retrieval from a Qdrant vector store seeded with Swiss federal law.

## Requirements

- Python 3.12
- [uv](https://github.com/astral-sh/uv) package manager
- A [Qdrant Cloud](https://cloud.qdrant.io/) free-tier cluster (1 GB is plenty for the 36 article corpus)
- An [Anthropic](https://console.anthropic.com/settings/keys) API key

## Provisioning Qdrant Cloud

1. Sign in to <https://cloud.qdrant.io/> and create a free-tier cluster (any region close to Switzerland, e.g. `eu-central` / Frankfurt).
2. Once the cluster is `Healthy`, copy its HTTPS URL — it looks like `https://<id>.eu-central.aws.cloud.qdrant.io:6333`. That's `QDRANT_URL`.
3. Open the cluster's **API keys** tab, click **Create API key**, and copy the value. That's `QDRANT_API_KEY`.

The collection name (`QDRANT_COLLECTION`, default `swiss_law`) is created automatically by the seed script with 384-dim cosine vectors and keyword payload indexes on `sr_number`, `article`, and `language`. No manual cluster setup is needed beyond creating the cluster and the API key.

On Replit, store both values in **Tools → Secrets** (not in `.env`); on local machines, put them in `backend/.env` per the setup below.

## Setup

```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv and install dependencies
uv python install 3.12
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Copy and populate secrets (local development only — Replit uses the Secrets pane)
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY, QDRANT_URL, QDRANT_API_KEY

# Seed Qdrant (one-time per cluster, plus whenever seed/law_articles.json changes)
# Optional: ingest cantonal corpora (ZH/BE/GE) before seeding so they ship in the same upsert.
python -m swiss_legal_api.ingest.cantonal --canton ZH,BE,GE
python -m swiss_legal_api.seeding.seed_qdrant

# Start the API
uvicorn swiss_legal_api.api.main:app --host 0.0.0.0 --port 8000
```

After seeding you should see `Seeded N articles into swiss_law` and `curl http://localhost:8000/readyz` should return `{"ok":true,"qdrant":"reachable"}`.

To run the full smoke gate (lint, types, unit tests, live scans of all three personas, plus a Qdrant collection sanity check) against an already-running API — for example the Replit `Start application` workflow — set `USE_EXTERNAL_API=1`:

```bash
cd backend
USE_EXTERNAL_API=1 bash scripts/smoke.sh
```

Without that flag, `smoke.sh` spins up its own uvicorn on port 8000 (which would conflict with the workflow).

Swagger UI: http://localhost:8000/docs

## End-to-End Test

```bash
curl -X POST http://localhost:8000/scan \
  -H "content-type: application/json" \
  -d @fixtures/luis_profile.json
```

## Health Endpoints

| Path                          | Purpose                                                       |
| ----------------------------- | ------------------------------------------------------------- |
| `/health`                     | Cheap liveness — proves the process is up.                    |
| `/readyz`                     | Deep readiness — pings Qdrant; 503 if unreachable.            |
| `/readyz?include=curriculum`  | Same plus a check that the curriculum collection exists. 503 if Qdrant is reachable but the curriculum collection is missing. |

`/readyz` is what a load balancer should poll. `/health` is for the process supervisor.
Use `?include=curriculum` only on deployments that have actually seeded
doctrinal PDFs — otherwise the bootstrap deployment will fail readiness.

## Trusted curriculum (advisory doctrine)

A second Qdrant collection (`co_curriculum` by default, override via
`CURRICULUM_COLLECTION`) holds embeddings of trusted doctrinal text — the
default seed target is the Code of Obligations articles 1-183 plus a small
set of hand-picked specialized PDFs. **Doctrine is advisory only:** the
verifier is allowed to read these chunks for context, but the citation
contract is unchanged — `Benefit.citations[]` always carries SR + article
authority. The doctrine surfaces on `Benefit.supporting_doctrine[]` for
transparency (the frontend renders it under a "Why this applies"
disclosure visually distinct from the binding "Legal basis" block) and is
never the basis of a verification.

### Contributor workflow

1. Drop a PDF under `backend/seed/curriculum/<stem>.pdf`. Pick a stable,
   human-readable stem (e.g. `co_articles_1_183`) — the stem is part of
   the chunk's UUID5 ID, so renaming a PDF orphans its existing points
   until reconciliation runs.
2. Optionally, drop a sidecar `<stem>.meta.json` with any of:

   ```json
   {
     "language": "en",
     "topic_tags": ["contracts", "errors"],
     "chapter_index": {
       "1":  "Chapter 1: Formation",
       "12": "Chapter 2: Errors"
     }
   }
   ```

   `chapter_index` is sparse — list only the *first* page of each chapter
   and the chunker forward-fills the label across the chapter's pages.
3. Re-seed:

   ```bash
   python -m swiss_legal_api.seeding.seed_curriculum
   ```

   The seeder creates the collection on first run, derives stable IDs from
   `(source_doc, page, chunk_index)` so re-runs upsert in place, and
   prints per-PDF chunk counts.

### Citation vs. doctrine — at a glance

| Field                        | Source                       | Authoritative? | Where surfaced                     |
| ---------------------------- | ---------------------------- | -------------- | ---------------------------------- |
| `Benefit.citations[]`        | `swiss_law` (SR + article)   | Yes            | "Legal basis" — every Benefit      |
| `Benefit.supporting_doctrine[]` | `co_curriculum` (PDFs)    | No             | "Why this applies" — when present  |

If the curriculum collection is missing or unreachable the verifier
soft-fails (no doctrine attached, scan returns normally). Use
`/readyz?include=curriculum` if your deployment depends on doctrine being
present.

## Configuration

All settings are read from the environment (see `.env.example`).

| Variable               | Default                                | Notes                                                                                          |
| ---------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`    | (empty)                                | Required for live `/scan` and `/chat`.                                                         |
| `CLAUDE_MODEL`         | `claude-opus-4-7`                      | Override per environment if needed.                                                            |
| `QDRANT_URL`           | (empty)                                | Required for readiness and live verified scans. Lifespan pings it but only logs a warning if unreachable; `/readyz` returns 503 in that case. |
| `QDRANT_API_KEY`       | (empty)                                | Required for Qdrant Cloud.                                                                     |
| `QDRANT_COLLECTION`    | `swiss_law`                            |                                                                                                |
| `CURRICULUM_COLLECTION`| `co_curriculum`                        | Second Qdrant collection for advisory doctrinal context (CO 1-183 + specialized PDFs). Only created when the curriculum seeder runs.|
| `EMBEDDING_MODEL`      | `intfloat/multilingual-e5-small`       | Pre-warmed at startup.                                                                         |
| `SCAN_CONCURRENCY`     | `3`                                    | Anthropic semaphore.                                                                           |
| `LOG_LEVEL`            | `INFO`                                 | `DEBUG` / `INFO` / `WARNING` / `ERROR`.                                                        |
| `FRONTEND_ORIGIN`      | (empty)                                | Single CORS origin to allow. Mutually exclusive with `CORS_ALLOW_ORIGINS`.                     |
| `CORS_ALLOW_ORIGINS`   | (empty)                                | Comma-separated CORS origins. Wins over `FRONTEND_ORIGIN` if both set.                         |
| `APP_ENV`              | `development`                          | Set to `production` (or `prod`) to make CORS origins mandatory — startup fails if neither origin var is set. |

### CORS

If neither `FRONTEND_ORIGIN` nor `CORS_ALLOW_ORIGINS` is set in development
(`APP_ENV=development`, the default), the API falls back to `allow_origins=["*"]` and
emits a single `WARNING` log line at startup. In production (`APP_ENV=production`),
the same misconfiguration **refuses to start** — startup raises `RuntimeError` rather
than silently fail open.

```bash
# Single origin (most common)
export FRONTEND_ORIGIN=https://app.example.ch

# Multiple origins (e.g. staging + production)
export CORS_ALLOW_ORIGINS=https://app.example.ch,https://staging.example.ch
```

## Logging

Structured single-line JSON-ish logs go to stdout (timestamp, level, logger, message).
Notable log lines emitted by the engine:

- `scan_complete profile_hash=… triggered=N verified=M suppressed=K duration_ms=…`
- `claude_verify entitlement_id=… latency_ms=… input_tokens=… output_tokens=…`
- `verify_entitlement failed for entitlement_id=… exc_type=…` (was previously silent)

500 responses on `/scan` and `/chat` always log the full exception server-side and return
only `{"detail": "Internal error"}` to the client — never `str(exc)` (which can leak
Anthropic API keys, request bodies, etc.).

## Refreshing the corpus from Fedlex

The 36-row hand-pasted seed (`seed/law_articles.json`) was the bootstrap; the
production corpus is now built from the federal SPARQL endpoint at
`data.fedlex.admin.ch`. The pipeline lives in
`src/swiss_legal_api/ingest/fedlex.py` and runs as a stand-alone CLI:

```bash
cd backend
python -m swiss_legal_api.ingest.fedlex \
  --sr 220,642.11,141.0,142.20,837.0,831.40 \
  --languages de,fr,it,en
# writes seed/law_articles.fedlex.json (sorted by SR / article / paragraph / language)
```

What it does, per SR number:

1. **SPARQL** the act URI, `dateEntryInForce`, optional `dateNoLongerInForce`
   and the per-language realisation URIs via the JOLux predicate
   `historicalLegalId`.
2. **Download** the consolidated Akoma Ntoso XML for each language present on
   the act from the Fedlex filestore. Fedlex serves several revisions of each
   consolidation behind the suffix `…-xml-N.xml` and the SPA HTML shell for
   non-existent N values, so the client probes `N=10..1` and keeps the highest
   that returns real `application/xml`.
3. **Parse** each `<article eId="art_X">` into one record per
   `<paragraph eId="art_X/para_Y">`. Articles without explicit paragraph
   children emit a single record with `paragraph="1"`. The `<num>` element
   (and any `<authorialNote>` it nests) is stripped so amendment commentary
   never bleeds into the embedding text.
4. **Emit** sorted JSON with the columns the seeder expects:
   `eli_uri, sr_number, article, paragraph, language, text, canton,
   effective_date, repealed_date`.

The seeder picks `seed/law_articles.fedlex.json` automatically when present
and falls back to the manual file otherwise:

```bash
python -m swiss_legal_api.seeding.seed_qdrant
# or pin a source explicitly:
python -m swiss_legal_api.seeding.seed_qdrant --source seed/law_articles.fedlex.json
```

Point IDs are derived as
`uuid5(NAMESPACE, "{eli_uri}|{article}|{paragraph}|{language}")` so re-running
the seeder over a refreshed snapshot upserts in place rather than churning
the collection. Manual entries (no `eli_uri`) live in the `manual:` ID
namespace so a future Fedlex-derived row for the same article cannot
collide with the bootstrap row it replaces.

### Snapshot date fallback

Fedlex publishes a 1 January consolidation per act per year, but not every
act gets a fresh consolidation every year. The CLI defaults to today's
`{YYYY}0101` and walks one year backwards down to the act's
`dateEntryInForce` if the requested date has no XML manifestation, logging
`fedlex_xml_fallback sr=… requested=… using=…` whenever it has to drop
back. A handful of acts (notably **SR 141.0 / Bürgerrechtsgesetz** as of
this writing) do not publish a downloadable AN-XML at any date — those
emit `fedlex_xml_missing sr=…` and silently skip; the seeder then keeps
serving those articles from the manual `seed/law_articles.json` bootstrap
**only for rows that contain real legal text**. The seeder filters out
any row whose text is the `__PENDING_FEDLEX_VERBATIM__` sentinel and
also hard-fails if a sentinel ever reaches the embedding loop, so a
half-backfilled bootstrap can never pollute Qdrant with placeholder
text.

### Tests

Tests for the parser and the snapshot determinism live in
`tests/test_fedlex_ingest.py`; they stub Fedlex via `respx` so they run
offline against the recorded fixtures under `tests/fixtures/fedlex/`.

## Cantonal corpora (ZH, BE, GE)

Cantonal Systematic Compilations are scraped per-canton because there is
no unified SPARQL endpoint analogous to Fedlex. Adapters live under
`src/swiss_legal_api/ingest/cantonal/` and all return the same record
shape (`CantonalArticleRecord`) so the CLI and seeder treat them
uniformly:

- `zurich_ls.py`  — Zurich Loseblattsammlung (ZH-Lex). HTML index +
  per-act HTML pages. `discover_specs()` walks the catalogue index at
  `Inhalt.html` and emits one spec per in-force act.
- `bern_bsg.py`   — Bern BSG / Belex. HTML index + per-act HTML or PDF.
  PDF entries flagged in the catalogue (`data-format="pdf"`) are
  routed through `parse_pdf_articles()` (pypdf text extraction +
  `Art. N` / paragraph-numeral splitter), so PDF-only acts land in
  the corpus alongside HTML.
- `geneva_rs.py`  — Geneva RSG. **OData feed** at
  `https://ge.ch/legislation/rsg/odata/Acts` is the primary surface;
  `parse_odata_feed()` reads the Atom XML and `discover_specs()`
  fetches it. Per-act bodies still come from the lexfind/ge.ch HTML.

Each record carries a `canton` payload field; retrieval already filters
on `canton ∈ {profile_canton, "CH"}`, so cantonal rows naturally
partition without any extra collection. Stable IDs use
`eli_uri = cantonal:{canton}:{compilation_id}` so a cantonal "412.31"
never collides with a hypothetical federal "412.31".

Geneva compilation IDs use a letter+number format (e.g. `RS A 2 05`).
We encode them as `A2.05` (drop spaces, dot before the trailing pair) so
the loosened `Citation.sr_number` regex (`^[A-Z]*\d+(\.\d+)?$`) accepts
them. The frontend's citation renderer reverses the encoding for display.

### Bootstrapping cantonal seed

```bash
# Default: walk each canton's catalogue index (HTML for ZH/BE, OData
# for GE) and ingest every in-force act. Emits the deterministic
# snapshot at seed/law_articles.cantonal.json.
python -m swiss_legal_api.ingest.cantonal --canton ZH,BE,GE

# Offline / smoke fallback: ingest only the small inline starter spec
# list (one act per canton). Useful when a canton's index is briefly
# unreachable, or when bootstrapping a fresh checkout that doesn't yet
# have network access to the cantonal portals.
python -m swiss_legal_api.ingest.cantonal --use-starter-specs

# The seeder auto-merges that file alongside fedlex+manual on the next reseed.
python -m swiss_legal_api.seeding.seed_qdrant
```

### End-to-end smoke gate

`fixtures/bern_tenant_profile.json` is a Bern tenant persona that
triggers `bern_rental_conciliation_free_procedure` (cites BSG 661.11
Art. 11 §3 — a record only present in the cantonal seed file).
`scripts/smoke.sh` runs this scan after the federal personas and
asserts both `>=1 verified` and that the cantonal entitlement ID is
present, so a green smoke proves the cantonal pipeline is wired
end-to-end.

Run order on a fresh cluster:

```bash
python -m swiss_legal_api.ingest.cantonal --use-starter-specs  # or full discovery
python -m swiss_legal_api.seeding.seed_qdrant
bash scripts/smoke.sh
```

### Tests

`tests/test_cantonal_ingest.py` covers, for all three adapters against
literal HTML/XML fixtures under `tests/fixtures/cantonal/`:

- per-act parser: article extraction, canton tagging, paragraph
  normalisation, repealed-article detection (including marker-after-
  paragraphs ordering for BE/GE), and nested-`<div>` alinéa preservation
  for Geneva;
- catalogue index discovery: ZH-Lex `Inhalt.html`, BSG `data/index/de`,
  and Geneva OData feed all yield specs scoped to currently in-force
  acts only;
- Bern PDF fallback: `parse_pdf_text` splits articles + numeric
  paragraph numerals from extracted lectern text, and `ingest()` routes
  `application/pdf` responses through the PDF parser end-to-end (with a
  hand-built one-page PDF round-trip);
- snapshot determinism + seeder cantonal auto-merge.

Networked `ingest()`/`discover_specs()` calls are stubbed via `respx`
so the suite runs offline.

## Source Languages

Fedlex publishes a downloadable English consolidated text for **SR 220** (Code of
Obligations) only. The other laws referenced by the seed corpus are not available
in English, only in DE / FR / IT. Per the v3 spec's "no paraphrased law text" rule, the
seed therefore mixes verbatim **EN** for SR 220 and verbatim **DE** for the rest:

| SR        | Title                                               | Source language used | Articles in seed                                       | Fedlex URL                                                                  |
| --------- | --------------------------------------------------- | -------------------- | ------------------------------------------------------ | --------------------------------------------------------------------------- |
| `220`     | Code of Obligations (OR / CO)                       | EN                   | 1, 18, 24, 28, 41, 42, 43, 62, 63, 197, 257e, 270a, 271, 321c, 327a, 328, 329f, 331, 335, 335c | https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en                        |
| `141.0`   | Swiss Citizenship Act (BüG / LN)                    | DE                   | 9, 11                                                   | https://www.fedlex.admin.ch/eli/cc/2016/404/de                              |
| `142.20`  | Foreign Nationals and Integration Act (AIG / LEI)   | DE                   | 43, 44                                                  | https://www.fedlex.admin.ch/eli/cc/2007/758/de                              |
| `642.11`  | Direct Federal Tax Act (DBG / LIFD)                 | DE                   | 9, 26, 27, 33 Abs 1, 33 Abs 3, 35, 36 Abs 2, 89, 99a, 212 | https://www.fedlex.admin.ch/eli/cc/1991/1184_1184_1184/de                   |
| `831.40`  | Occupational Pensions Act (BVG / LPP)               | DE                   | 1                                                       | https://www.fedlex.admin.ch/eli/cc/1983/797_797_797/de                      |
| `837.0`   | Unemployment Insurance Act (AVIG / LACI)            | DE                   | 8                                                       | https://www.fedlex.admin.ch/eli/cc/1982/2184_2184_2184/de                   |

Each entry in `seed/law_articles.json` declares its source language in its `language`
field, and each `quote_under_15_words` slice in `seed/entitlements.json` is a literal
copy from the corresponding article in the same language. The verification prompt
(`engine/verify.py`) explicitly states that retrieved DE text is treated as authoritative
alongside EN — Claude reasons natively in both languages.

### Verification

Before relying on this corpus for any production legal advice, spot-check each `text`
field against the Fedlex URL above for its `sr_number`. The DE entries were captured
from Fedlex consolidated text but Fedlex amends the consolidated versions when the laws
are revised, so the seed should be re-checked at every release cut.

> Note: SR 142.20 Art. 44 Abs. 1 lit. d in the seed reads `Landesprache` (single
> `s`), which is the verbatim spelling currently published on Fedlex (a known
> drafting typo — compare Art. 43 Abs. 1 lit. d, which reads `Landessprache`).
> Do not "correct" it — the verification pipeline expects the seed to match
> Fedlex character-for-character.

### Dropped Articles

None. Every entitlement in `seed/entitlements.json` resolves to an article in
`seed/law_articles.json` after the EN+DE rewrite. If a future spec change requires an
article that has no Fedlex EN translation **and** is not reproducible verbatim in DE,
list it here with the reason and remove the dependent entitlement.

## Permit-Status Sprint (Option C)

The catalog now distinguishes Swiss residents from foreign permit holders.
`ContextProfile` carries three permit-status fields:

| Field                   | Type / values                                                       | Default  |
| ----------------------- | ------------------------------------------------------------------- | -------- |
| `permit_type`           | `none`, `B`, `C`, `L`, `F`, `N`, `S`, `G`, `Ci`                     | `none`   |
| `nationality_status`    | `swiss`, `eu_efta`, `third_country`                                 | `swiss`  |
| `years_in_switzerland`  | `int` ≥ 0, ≤ 100, or `null` (user-supplied; not derived)            | `null`   |

The defaults preserve backward compatibility: a fixture that omits these
fields evaluates as a Swiss resident with no permit, exactly the regression
behaviour the Luis fixture relied on before the sprint.

### New entitlements

| ID                                       | Citation             | Trigger gist                              |
| ---------------------------------------- | -------------------- | ----------------------------------------- |
| `quellensteuer_subsequent_assessment`    | DBG (SR 642.11) Art. 99a | B permit + non-Swiss                     |
| `naturalisation_eligibility`             | BüG (SR 141.0) Art. 9    | C permit + ≥10 yrs + non-Swiss            |
| `family_reunification_right`             | AIG (SR 142.20) Art. 43  | B/C permit + non-Swiss + (married OR kids) |

### Catalog validator

`scripts/validate_catalog.py` walks every trigger expression in
`seed/entitlements.json`, extracts the field paths referenced by leaf
operators, and asserts that each top-level field exists on `ContextProfile`.
It also validates that any `event_within_years` event name is a real
`LifeEventKind`. The validator is wired into `scripts/smoke.sh` as a hard
gate that runs before the unit tests, so a new entitlement that references
a typo'd profile field fails CI immediately rather than at scan time.

### Persona fixtures

- `fixtures/luis_profile.json` — Swiss, ZH, married, 2 kids (regression baseline).
- `fixtures/b_permit_eu_employee.json` — EU/EFTA, B permit, VD, single, 3 yrs in CH (Quellensteuer persona).
- `fixtures/c_permit_third_country.json` — third country, C permit, GE, married + 1 kid, 11 yrs in CH (naturalisation persona).

### Trigger-DSL constraint

The sprint did **not** add any new trigger operators. All permit-status
gating is expressed with the existing 12 operators (notably `eq`, `in`,
`not`, `gte`, `any`).

## Trigger DSL

The trigger DSL (`schemas/trigger_dsl.py`) is a Pydantic v2 tagged union dispatched
through a callable `Discriminator`. Each variant carries a `kind: Literal[…]` field for
OpenAPI clarity. Existing JSON like `{"eq": [...]}` parses unchanged — the discriminator
infers the tag from the operator key when `kind` is missing — so seed and fixture data
do not need migration. All variants set `extra="forbid"` so payloads that smuggle two
operators in one node (e.g. `{"eq": [...], "gt": [...]}`) fail loudly instead of
silently dropping the unmatched branch.

## Legal Disclaimer

This software is not a substitute for advice from a Swiss attorney registered with a cantonal bar.
