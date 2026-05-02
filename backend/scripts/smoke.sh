#!/usr/bin/env bash
set -euo pipefail

echo "=== Lint + types ==="
ruff check src tests
mypy src

echo "=== Catalog validator (trigger fields ↔ ContextProfile) ==="
python scripts/validate_catalog.py

echo "=== Unit tests (offline) ==="
pytest tests/test_schemas.py tests/test_seed.py tests/test_trigger.py tests/test_invariants.py -v

echo "=== Start API ==="
uvicorn swiss_legal_api.api.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null || true" EXIT
sleep 4

echo "=== Health ==="
curl -sf http://localhost:8000/health

echo "=== OpenAPI paths ==="
curl -sf http://localhost:8000/openapi.json | python -c "import sys, json; d=json.load(sys.stdin); print(list(d['paths'].keys()))"

echo "=== Live scan (Luis profile — Swiss regression baseline) ==="
RESP=$(curl -sf -X POST http://localhost:8000/scan \
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

echo "=== Live scan (b_permit_eu_employee — Quellensteuer persona) ==="
RESP=$(curl -sf -X POST http://localhost:8000/scan \
  -H "content-type: application/json" \
  -d @fixtures/b_permit_eu_employee.json \
  --max-time 180)
echo "$RESP" | python -c "
import sys, json
r = json.load(sys.stdin)
print(f\"b_permit benefits returned: {len(r['benefits'])}, suppressed: {r['suppressed_count']}\")
"

echo "=== Live scan (c_permit_third_country — naturalisation persona) ==="
RESP=$(curl -sf -X POST http://localhost:8000/scan \
  -H "content-type: application/json" \
  -d @fixtures/c_permit_third_country.json \
  --max-time 180)
echo "$RESP" | python -c "
import sys, json
r = json.load(sys.stdin)
print(f\"c_permit benefits returned: {len(r['benefits'])}, suppressed: {r['suppressed_count']}\")
"

echo "=== Export OpenAPI ==="
python scripts/export_openapi.py

echo "=== Backend smoke PASSED ==="
