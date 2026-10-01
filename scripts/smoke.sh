#!/usr/bin/env bash
# Verifica que el backend responde y que un encargo de la fábrica llega a
# "terminado".
#   ./scripts/smoke.sh
#
# Solo lanza el encargo con el cerebro guionado: con uno real (claude-cli,
# anthropic, openai-compatible) gastaría cupo o saldo. Para forzarlo igual:
#   FORZAR=1 ./scripts/smoke.sh
set -euo pipefail

API="${API:-http://localhost:8000}"

echo "== Salud =="
SALUD="$(curl -sf "$API/api/health")" || { echo "El backend no responde en $API" >&2; exit 1; }
echo "$SALUD"
echo

if ! echo "$SALUD" | grep -q '"cerebro_activo":"scripted"' && [ "${FORZAR:-0}" != "1" ]; then
  echo "El cerebro activo no es el guionado; no se lanza un encargo (FORZAR=1 para hacerlo)."
  exit 0
fi

echo "== Encargo de prueba =="
ENCARGO="$(curl -sf -X POST "$API/api/fabrica/encargos" -H 'Content-Type: application/json' \
  -d '{"pedido":"Registrar productos con nombre y precio. Calcular el total de un carrito con impuestos."}')"
ID="$(echo "$ENCARGO" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')"
echo "Encargo $ID"

for _ in $(seq 1 60); do
  ESTADO="$(curl -sf "$API/api/fabrica/encargos/$ID" | sed -n 's/.*"estado":"\([^"]*\)".*/\1/p')"
  case "$ESTADO" in
    terminado) echo "Estado: terminado"; break ;;
    fallido|esperando_humano|interrumpido) echo "Estado inesperado: $ESTADO" >&2; exit 1 ;;
  esac
  sleep 1
done
[ "$ESTADO" = "terminado" ] || { echo "El encargo no terminó a tiempo (estado: $ESTADO)" >&2; exit 1; }

echo -e "\n== Bitácora =="
curl -sf "$API/api/fabrica/encargos/$ID/bitacora" | grep -o '"integra":[a-z]*'

echo -e "\n== Salud de la fábrica =="
curl -sf "$API/api/fabrica/salud" | grep -o '"estado_general":"[a-z]*"'
