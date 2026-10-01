# Orquesta

Fábrica de software agéntica: un pedido en lenguaje natural pasa por el
Especificador, el Implementador, el Revisor, el Diagnosticador (si hay
rechazo), el Verificador y el Despliegue, coordinados por el Líder, con
telemetría en vivo por WebSocket. Orquestación con `asyncio` puro — nada de LangGraph, CrewAI, AutoGen ni
LlamaIndex. Única excepción, decidida por una persona: Prefect como
capa **opcional de observabilidad** de la fábrica
(`FABRICA_ORQUESTADOR=prefect`, `orchestrator/prefect_opcional.py`). Prefect
observa; el Líder sigue decidiendo orden, reintentos y paralelismo con
asyncio, y sin el paquete instalado nada cambia. Ver `README.md` para cómo
arrancar y qué hace cada pieza.

## Arquitectura: puertos y adaptadores en los bordes

Hexagonal, pero solo en las tres fronteras de infraestructura — no en todo el
código. Dirección de dependencias, estricta:

- `backend/app/dominio/` no importa `fastapi`, `sqlalchemy`, `httpx`, `os` ni
  `app.config`. Entidades como dataclasses, puertos como `Protocol`, casos de
  uso que reciben sus puertos por constructor. Esto se verifica con AST en
  `backend/tests/test_arquitectura.py` — si lo rompes, el test lo dice.
- `backend/app/adaptadores/` implementa esos puertos (SQLAlchemy, cerebros
  Anthropic/Claude CLI/compatible con OpenAI/guionado, ejecutor de pruebas
  local y Docker, despliegue a GitHub real y simulado, bus en memoria). Puede
  importar de `dominio/`, nunca al revés.
- `backend/app/api/` y `backend/app/websocket/` son adaptadores de entrada:
  traducen HTTP/WS a llamadas del Líder y de `dominio/salud.py`. No contienen
  reglas de negocio.
- El cableado — qué adaptador concreto se usa — vive en
  `adaptadores/fabricas.py`, `main.py` y `config.py`. Ningún otro módulo decide
  implementaciones.
- `backend/app/orchestrator/` y `backend/app/agents/` quedan fuera de este
  esquema a propósito: son lógica de aplicación (el *cuándo* y el *qué*), no
  infraestructura. No los pongas detrás de un puerto.

Si vas a agregar una abstracción nueva, pregúntate si ya hay dos
implementaciones reales o un motivo concreto de prueba. Si no, no la crees.

## La regla crítica del paralelismo

**Los agentes que trabajan en worktrees no levantan servidores** (`uvicorn`,
`npm run dev`, `npm start`). Verifican de forma estática:

```bash
# backend
python -c "import app.main"
ruff check . && ruff format --check .
mypy app/dominio
pytest -q

# frontend
npx tsc --noEmit
npm run build
```

La ejecución real — `./scripts/smoke.sh`, el panel en el navegador — ocurre
**después de fusionar**, en la rama principal, vía el agente `revisor`.

Motivo: cada worktree es un checkout limpio, sin `node_modules` ni `.venv`
propios instalados de antemano, y dos servidores del mismo proyecto pelean por
los puertos 8000 y 3000. Levantar un servidor en un worktree paralelo es la
forma más rápida de que dos agentes se pisen sin darse cuenta.

## El contrato congelado

Todo evento que cruza el WebSocket tiene esta forma, sin excepciones:

```json
{ "agent": "backend", "status": "running", "msg": "…", "ts": "…", "run_id": "…", "artifacts": [] }
```

`agent`, `status` y `msg` son obligatorios; el resto es opcional para que un
cliente antiguo no se rompa. Cualquier agente nuevo que emita eventos usa
exactamente esta forma (`dominio.modelos.EventoAgente`). Nadie lo modifica sin
que una persona lo decida explícitamente — no es una decisión que un agente
tome solo porque le convendría un campo más.

## Territorios

| Si la tarea toca...                                    | Vive en...                          |
|----------------------------------------------------------|--------------------------------------|
| Reglas de la fábrica (dependencias, política, bitácora), salud, puertos, errores | `backend/app/dominio/` |
| SQLAlchemy, cerebros, ejecutor de pruebas, despliegue, bus | `backend/app/adaptadores/`          |
| Endpoints HTTP / WebSocket                                | `backend/app/api/`, `backend/app/websocket/` |
| Un agente de la fábrica                                   | `backend/app/agents/fabrica/`        |
| El pipeline: orden, reintentos, paralelismo, pausas humanas, plugins | `backend/app/orchestrator/` |
| El panel de la fábrica, componentes React                 | `frontend/app/`, `frontend/components/` |
| Llamadas HTTP del frontend, tipos compartidos             | `frontend/lib/`                      |

## Una trampa conocida en `api/`

No pongas `from __future__ import annotations` en un módulo de `app/api/`
que tenga una ruta `status_code=204` con retorno `-> None`. FastAPI infiere
mal el response_model cuando la anotación de retorno llega como string en vez
de `NoneType`, y explota al arrancar con "Status code 204 must not have a
response body". `dominio/`, `adaptadores/` y `agents/` no tienen este
problema — es específico de cómo FastAPI resuelve las anotaciones de las
rutas. Ya pasó tres veces (`api/items.py`, `api/vercel.py`, `api/render.py`).

## Despliegue

`DEPLOY_ENABLED=false` es el valor por defecto y **no cambia**. Un agente que
despliega a producción sin que una persona lo pida es un incidente esperando a
ocurrir. Ver la sección de despliegue del README para las opciones reales.

## Idioma

Español en código, nombres, mensajes de error, interfaz y commits — igual que
el resto del repositorio.
