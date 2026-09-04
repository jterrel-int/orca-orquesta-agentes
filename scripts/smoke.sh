#!/usr/bin/env bash
# Verifica que el backend responde y que una corrida completa funciona.
#   ./scripts/smoke.sh
set -euo pipefail

API="${API:-http://localhost:8000}"

echo "== Salud =="
curl -sf "$API/api/health" || { echo "El backend no responde en $API" >&2; exit 1; }
echo

echo -e "\n== Corrida de agentes =="
curl -sf -X POST "$API/api/run"
echo
sleep 5

echo -e "\n== Estado final =="
curl -sf "$API/api/run/status"
echo

echo -e "\n== CRUD =="
curl -sf -X POST "$API/api/items" -H 'Content-Type: application/json' -d '{"name":"prueba de humo"}'
echo
curl -sf "$API/api/items"
echo
