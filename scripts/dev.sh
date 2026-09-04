#!/usr/bin/env bash
# Levanta backend y frontend en local, sin Docker.
#   ./scripts/dev.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

limpiar() { echo; echo "Deteniendo…"; kill 0; }
trap limpiar EXIT INT TERM

echo "== Backend =="
cd "$RAIZ/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements.txt
fi
./.venv/bin/uvicorn app.main:app --reload --port 8000 &

echo "== Frontend =="
cd "$RAIZ/frontend"
[ -d node_modules ] || npm install
npm run dev &

echo
echo "  Panel:    http://localhost:3000"
echo "  API docs: http://localhost:8000/docs"
echo "  Ctrl+C para detener ambos"
wait
