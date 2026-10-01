#!/usr/bin/env bash
# Despliegue manual del frontend de Orquesta a Vercel. Deliberadamente
# separado de los agentes: un agente que despliega a producción sin que una
# persona lo pida es un incidente esperando a ocurrir.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ/frontend"

command -v vercel >/dev/null 2>&1 || {
  echo "El CLI de Vercel no está instalado. Instálalo con: npm i -g vercel" >&2
  exit 1
}

echo "Desplegando el frontend a producción…"
echo "Directorio: $(pwd)"
echo

# La primera vez, vercel pregunta a qué proyecto vincular. Es esperado.
vercel --prod
