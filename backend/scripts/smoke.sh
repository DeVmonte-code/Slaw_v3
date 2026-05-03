#!/usr/bin/env bash
set -euo pipefail

# When USE_EXTERNAL_API=1, smoke.sh skips spinning up its own uvicorn and
# targets API_BASE_URL (default http://localhost:8000) instead. Useful when
# a workflow is already serving the API on port 8000.
#
# Note: the "Qdrant corpus sanity" step below probes Qdrant directly using
# this shell's QDRANT_URL / QDRANT_API_KEY / QDRANT_COLLECTION env vars,
# so external mode assumes the smoke runner shares Qdrant config with the
# remote API. On Replit that's automatic (workflow + shell read the same
# Secrets); against a truly remote API, export the matching values first.
USE_EXTERNAL_API="${USE_EXTERNAL_API:-0}"
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

echo "=== Lint + types ==="
ruff check src tests
mypy src

echo "=== Catalog validator (trigger fields ↔ ContextProfile) ==="
python scripts/validate_catalog.py

echo "=== Unit tests (offline) ==="
pytest tests/test_schemas.py tests/test_seed.py tests/test_trigger.py tests/test_invariants.py -v

if [ "$USE_EXTERNAL_API" = "1" ]; then
  echo "=== Reusing external API at $API_BASE_URL ==="
else
  echo "=== Start API ==="
  uvicorn swiss_legal_api.api.main:app --host 0.0.0.0 --port 8000 &
  SERVER_PID=$!
  trap "kill $SERVER_PID 2>/dev/null || true" EXIT
  sleep 15
fi

echo "=== Health ==="
curl -sf "$API_BASE_URL/health"
echo

echo "=== Readiness (Qdrant reachable) ==="
curl -sf "$API_BASE_URL/readyz"
echo

echo "=== Qdrant corpus sanity (collection exists with > 0 points) ==="
PYTHONPATH="${PYTHONPATH:-}:src" python - <<'PY'
import os, sys
from qdrant_client import QdrantClient
from swiss_legal_api.config import settings

client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=10.0)
collections = {c.name for c in client.get_collections().collections}
if settings.qdrant_collection not in collections:
    print(f"FAIL: collection '{settings.qdrant_collection}' missing. Found: {sorted(collections)}")
    sys.exit(1)
count = client.count(collection_name=settings.qdrant_collection, exact=True).count
print(f"Collection '{settings.qdrant_collection}' has {count} points")
if count <= 0:
    print("FAIL: collection is empty — run python -m swiss_legal_api.seeding.seed_qdrant")
    sys.exit(1)
PY

echo "=== OpenAPI paths ==="
curl -sf "$API_BASE_URL/openapi.json" | python -c "import sys, json; d=json.load(sys.stdin); print(list(d['paths'].keys()))"

echo "=== Live scan (Luis profile — Swiss regression baseline) ==="
RESP=$(curl -sf -X POST "$API_BASE_URL/scan" \
  -H "content-type: application/json" \
  -d @fixtures/luis_profile.json \
  --max-time 180)

COUNT=$(echo "$RESP" | python -c "import sys, json; print(len(json.load(sys.stdin)['benefits']))")
echo "Benefits returned: $COUNT"
if [ "$COUNT" -lt 5 ]; then
  echo "FAIL: expected >= 5 benefits, got $COUNT"
  exit 1
fi

echo "$RESP" | python -c "
import sys, json
ids = [b['entitlement_id'] for b in json.load(sys.stdin)['benefits']]
assert 'rent_reduction_reference_rate' in ids, 'rent_reduction missing'
assert 'childcare_cost_deduction' in ids, 'childcare_cost_deduction missing'
print('Luis required IDs present')
"

# Anthropic Opus ITPM (input-tokens-per-minute) is the tightest budget at tier 1.
# Luis burns most of it in ~12 concurrent verify calls; the next persona scan can
# rate-limit-fail every verify if we don't pause for the TPM window to roll.
INTER_PERSONA_SLEEP="${INTER_PERSONA_SLEEP:-60}"

echo "=== Cooling down ${INTER_PERSONA_SLEEP}s for Anthropic TPM window ==="
sleep "$INTER_PERSONA_SLEEP"

echo "=== Live scan (b_permit_eu_employee — Quellensteuer persona) ==="
RESP=$(curl -sf -X POST "$API_BASE_URL/scan" \
  -H "content-type: application/json" \
  -d @fixtures/b_permit_eu_employee.json \
  --max-time 180)
echo "$RESP" | python -c "
import sys, json
r = json.load(sys.stdin)
n = len(r['benefits'])
print(f\"b_permit benefits returned: {n}, suppressed: {r['suppressed_count']}\")
assert n >= 1, f'FAIL: b_permit_eu_employee expected >= 1 verified, got {n}'
"

echo "=== Cooling down ${INTER_PERSONA_SLEEP}s for Anthropic TPM window ==="
sleep "$INTER_PERSONA_SLEEP"

echo "=== Live scan (c_permit_third_country — naturalisation persona) ==="
RESP=$(curl -sf -X POST "$API_BASE_URL/scan" \
  -H "content-type: application/json" \
  -d @fixtures/c_permit_third_country.json \
  --max-time 180)
echo "$RESP" | python -c "
import sys, json
r = json.load(sys.stdin)
n = len(r['benefits'])
print(f\"c_permit benefits returned: {n}, suppressed: {r['suppressed_count']}\")
assert n >= 1, f'FAIL: c_permit_third_country expected >= 1 verified, got {n}'
"

echo "=== Cooling down ${INTER_PERSONA_SLEEP}s for Anthropic TPM window ==="
sleep "$INTER_PERSONA_SLEEP"

# Cantonal smoke gate (Task #21). Asserts the cantonal ingest +
# seed_qdrant pipeline actually surfaces a cantonal entitlement
# end-to-end. The bern_tenant_profile fixture triggers
# `bern_rental_conciliation_free_procedure`, which cites BSG 661.11
# Art. 11 §3 — a record only present in `seed/law_articles.cantonal.json`,
# so a green here proves the cantonal corpus is in Qdrant and the
# canton-scoped retrieval filter passes the row through.
echo "=== Live scan (bern_tenant — cantonal BSG entitlement) ==="
RESP=$(curl -sf -X POST "$API_BASE_URL/scan" \
  -H "content-type: application/json" \
  -d @fixtures/bern_tenant_profile.json \
  --max-time 180)
echo "$RESP" | python -c "
import sys, json
r = json.load(sys.stdin)
n = len(r['benefits'])
ids = [b['entitlement_id'] for b in r['benefits']]
print(f\"bern_tenant benefits returned: {n}, ids: {ids}\")
assert n >= 1, f'FAIL: bern_tenant expected >= 1 verified cantonal entitlement, got {n}'
assert 'bern_rental_conciliation_free_procedure' in ids, (
    f'FAIL: bern_rental_conciliation_free_procedure missing from {ids} — '
    'cantonal corpus may not be seeded into Qdrant. Run '
    '\"python -m swiss_legal_api.ingest.cantonal --use-starter-specs && '
    'python -m swiss_legal_api.seeding.seed_qdrant\" first.'
)
"

echo "=== Export OpenAPI ==="
python scripts/export_openapi.py

echo "=== Backend smoke PASSED ==="
