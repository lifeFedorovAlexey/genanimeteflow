#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
test -x .venv/bin/python || { echo "Run ./setup.sh first" >&2; exit 1; }
export PYTHONPATH="$ROOT/apps/api"
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
cleanup() { kill "$api_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
(cd apps/web && npm run dev -- --host 127.0.0.1)
