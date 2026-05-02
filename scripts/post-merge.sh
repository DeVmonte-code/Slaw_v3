#!/bin/bash
# Post-merge setup. Runs after every task merge.
# - Idempotent: safe to run multiple times.
# - Non-interactive: stdin is closed; use --yes/--force flags as needed.
# - Fail fast: `set -e` aborts on first error.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[post-merge] starting in $ROOT"

# Frontend (Next.js) — pnpm-based
if [ -f "frontend/package.json" ]; then
  echo "[post-merge] installing frontend deps (pnpm)"
  (cd frontend && pnpm install --frozen-lockfile=false)
fi

# Mockup sandbox (Vite) — npm-based, has package-lock.json
if [ -f "artifacts/mockup-sandbox/package.json" ]; then
  echo "[post-merge] installing mockup-sandbox deps (npm)"
  (cd artifacts/mockup-sandbox && npm install --no-audit --no-fund --prefer-offline)
fi

# Backend (FastAPI) — uv-managed, but the editable install is project-local.
# Only re-install when pyproject changed; uv handles its own caching.
if [ -f "backend/pyproject.toml" ]; then
  echo "[post-merge] backend deps managed by repl_setup; skipping"
fi

echo "[post-merge] done"
