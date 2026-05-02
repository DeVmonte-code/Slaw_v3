#!/usr/bin/env bash
set -e

# Start backend on port 8000 (background)
cd /home/runner/workspace/backend
PYTHONPATH=src uvicorn swiss_legal_api.api.main:app --host localhost --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for backend to start..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "Backend ready."
    break
  fi
  sleep 1
done

# Start frontend on port 5000
cd /home/runner/workspace/frontend
exec pnpm start
