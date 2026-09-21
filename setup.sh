#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v python3 >/dev/null || { echo "Python 3.11+ is required" >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js 20+ is required" >&2; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
(cd apps/web && npm install)
mkdir -p jobs assets/equipment motions/installed data logs
if command -v blender >/dev/null; then
  echo "Blender: available"
else
  echo "Blender: not installed; Blender-dependent stages remain unavailable" >&2
fi
PYTHONPATH="$ROOT/apps/api" .venv/bin/python -c 'from app.hardware import detect_hardware; import json; print(json.dumps(detect_hardware(), indent=2))'
echo "Setup complete. Start the API with PYTHONPATH=apps/api .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
