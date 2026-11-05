#!/usr/bin/env bash
# Start the API (port 8000) and the web app (port 5173) together. Ctrl+C stops both.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
[ -d .venv ] && source .venv/bin/activate && PY=python
( cd backend && $PY -m uvicorn app.main:app --port 8000 ) &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd frontend
[ -d node_modules ] || npm install
npm run dev
