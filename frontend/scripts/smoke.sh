#!/usr/bin/env bash
# End-to-end frontend smoke test.
# Run from the frontend/ directory with the "Start application" workflow STOPPED
# (otherwise port 5000 is already in use and `pnpm start &` will fail).
set -euo pipefail

BACKEND_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5000}"

echo "=== Verify backend reachable ==="
curl -sf "$BACKEND_URL/health"
curl -sf "$BACKEND_URL/openapi.json" | head -c 100 && echo

echo "=== Regenerate types ==="
pnpm run types:api

echo "=== Build ==="
pnpm build

echo "=== Start ==="
pnpm start &
WEB_PID=$!
trap "kill $WEB_PID 2>/dev/null || true" EXIT
sleep 6

echo "=== Check root page renders form ==="
HTML=$(curl -sf "http://localhost:${FRONTEND_PORT}")
echo "$HTML" | grep -q "Swiss Legal Rights Scan" && echo "PASS: title present"
echo "$HTML" | grep -q "Run Rights Scan" && echo "PASS: submit button present"

echo "=== Frontend smoke PASSED ==="
