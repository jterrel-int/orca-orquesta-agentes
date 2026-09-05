# Orquesta

MVP multiagente: tres agentes que generan código, lo ejecutan y lo despliegan,
con telemetría en vivo por WebSocket.

**Stack:** FastAPI + SQLite (async) · Next.js 15 App Router · WebSockets ·
orquestación con `asyncio` puro. Sin LangGraph, sin CrewAI.

---

## Arrancar

### Opción A — Docker (lo más simple)

```bash
docker compose up --build
```

Panel en `http://localhost:3000`, API en `http://localhost:8000/docs`.

### Opción B — local

**Linux / macOS**

```bash
./scripts/dev.sh
```

**Windows**

```powershell
.\scripts\dev.ps1
```

O a mano, en dos terminales:

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

### Comprobar que funciona

```bash
./scripts/smoke.sh
```

---

## Qué hace

Abre el panel y presiona **Ejecutar agentes**. Vas a ver tres tarjetas
cambiando de estado y los logs llegando en vivo. En unos segundos:

1. **BackendAgent** escribe `backend/app/generated/item_routes.py` — un router
   CRUD real de FastAPI. La app lo monta **sin reiniciarse**: recarga
   `/docs` y los endpoints ahora los sirve el código generado.
2. **FrontendAgent** escribe `frontend/app/items/ListaItems.tsx`. Next.js lo
   recarga en caliente; abre `/items` y ahí está.
3. **DeployAgent** ejecuta `vercel --prod`. Por defecto está apagado y solo
   registra el comando que correría.

No son logs simulados: los archivos aparecen en disco y el código generado se
verifica antes de escribirse.

---

## Arquitectura

```
backend/app/
  agents/          base.py · cerebros.py · backend_agent · frontend_agent · deploy_agent
  orchestrator/    eventos.py (bus pub/sub) · orquestador.py (etapas)
  websocket/       manager.py (retransmisión) · rutas.py (/ws)
  api/             items.py (CRUD) · corridas.py (/api/run)
  models/          item.py · eventos.py
  db/              session.py (SQLAlchemy async)
  generated/       ← lo que escriben los agentes
frontend/
  app/             page.tsx (panel) · items/ (CRUD)
  components/      AgentCard · LogStream · RunButton · EstadoPunto
  lib/             api.ts · ws.ts (reconexión) · types.ts
```

### Separación agente / orquestación

Un agente sabe **qué** hacer. El orquestador decide **cuándo** y **junto a
quién**. Un agente nunca llama a otro: se comunican dejando datos en
`ContextoCorrida.datos` — el `BackendAgent` deja ahí los endpoints y el
`FrontendAgent` los lee.

### Cómo paralelizar

Una corrida es una lista de *etapas*; cada etapa corre con `asyncio.gather`.
En `orchestrator/orquestador.py`:

```python
def etapas(self):
    return [[BackendAgent()], [FrontendAgent()], [DeployAgent()]]   # secuencial
```

Para correr backend y frontend a la vez, ponlos en la misma lista:

```python
    return [[BackendAgent(), FrontendAgent()], [DeployAgent()]]     # paralelo
```

No hay que tocar los agentes, ni el bus, ni el frontend.

### Cómo cambiar los agentes por LLMs

Ya está hecho. Los agentes no llaman a ninguna API: le piden contenido a su
`Cerebro` (`agents/cerebros.py`). Hay dos implementaciones tras el mismo
protocolo:

- `CerebroGuionado` — determinista, sin red, sin clave. **Por defecto.**
- `CerebroAnthropic` — llamada real a la API de mensajes.

En `.env`:

```
BRAIN=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Los agentes no cambian ni una línea. Y si la llamada falla, el cerebro cae al
respaldo determinista en vez de tumbar la corrida.

Detalle que importa: el `BackendAgent` **compila** el código antes de
escribirlo (`compile(codigo, ...)`), y el `FrontendAgent` verifica que exporte
por defecto. Un LLM puede devolver algo que no compila; sin esa verificación,
un agente es un generador de texto con permisos de escritura.

---

## Despliegue a Vercel

El `DeployAgent` está **apagado por defecto** (`DEPLOY_ENABLED=false`). Con eso
registra el comando exacto que ejecutaría y termina bien.

Para desplegar de verdad:

```bash
npm i -g vercel
cd frontend && vercel        # vincula el proyecto la primera vez
```

Luego, o bien manualmente:

```bash
./scripts/deploy.sh
```

O activando el agente en `.env`:

```
DEPLOY_ENABLED=true
VERCEL_TOKEN=...     # opcional; si no, usa tu sesión local
```

El agente lanza el subproceso real, transmite su stdout línea por línea al
panel, extrae la URL de producción y falla si el código de salida no es cero.

> El despliegue no corre dentro de Docker: el CLI de Vercel necesita tu sesión
> local. Ejecútalo en el anfitrión.

---

## MCP de Vercel

El repo trae `.mcp.json` versionado, con el servidor MCP de Vercel a nivel de
proyecto:

```bash
claude mcp add --scope project --transport http vercel https://mcp.vercel.com
```

Cualquiera que clone el repo lo tiene disponible sin configurar nada más.
Cosas que conviene saber:

- **Usa OAuth.** La primera vez que Claude Code lo usa, te pide autorizar en
  el navegador. No hay token que copiar a ningún archivo.
- **Los servidores de alcance de proyecto piden aprobación al iniciar
  sesión.** Vas a ver algo como `vercel: ⏸ Pending approval` en
  `claude mcp list` hasta que lo aceptes. Si el aviso no aparece solo,
  habilitalo a mano agregando `"enabledMcpServers": ["vercel"]` a
  `.claude/settings.local.json` (ese archivo es personal — está en
  `.gitignore`, no lo subas).
- **Alternativa:** `vercel mcp` configura Claude Code directamente desde el
  CLI de Vercel, y con `--project` apunta a la URL específica del proyecto ya
  vinculado en vez del endpoint compartido.
- **El MCP no despliega.** Sirve para buscar en la documentación de Vercel,
  listar proyectos y despliegues, y leer logs de build. El despliegue real lo
  hace el CLI (`vercel --prod`, ya sea a mano o vía `DeployAgent`). No hay
  código en este repo que espere desplegar a través del MCP.

Verificá que quedó andando con `claude mcp list` o `/mcp` dentro de una
sesión.

---

## API

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/health` | Salud, modo de cerebro y estado del deploy |
| POST | `/api/run` | Lanza el pipeline. `202` inmediato, `409` si ya corre uno |
| GET | `/api/run/status` | Resumen de la corrida actual |
| GET | `/api/events` | Historial en memoria, para clientes sin WebSocket |
| WS | `/ws` | Stream de eventos en vivo |
| GET/POST/PUT/DELETE | `/api/items` | CRUD de Item |

Formato de los eventos:

```json
{ "agent": "backend", "status": "running", "msg": "…", "ts": "…", "run_id": "…", "artifacts": [] }
```

`agent`, `status` y `msg` son los tres campos del contrato; el resto es opcional
y un cliente antiguo puede ignorarlos.

---

## Decisiones que quizá te sorprendan

**El despliegue automático está apagado.** Un agente que ejecuta `vercel --prod`
sin intervención humana, en ramas experimentales, despliega a producción cosas
que nadie revisó. Está implementado de verdad, con un flag para activarlo.

**El cerebro por defecto es determinista.** Un demo en vivo no debería depender
de una clave de API ni de que la red aguante. `BRAIN=anthropic` lo cambia.

**El WebSocket reenvía su historial al conectar.** Una pestaña abierta a mitad
de una corrida no se queda mirando una pantalla vacía.

**Un único consumidor del bus retransmite a todos los clientes**, en vez de una
suscripción por pestaña. El bus no crece con el número de pestañas abiertas.

**No se usa `next/font/google`.** Descarga las fuentes durante el build y lo
hace fallar sin red. Con `<link>`, sin conexión cae al stack del sistema.

---

## Variables de entorno

Copia `.env.example` a `.env`. Ninguna es obligatoria.

| Variable | Por defecto | Para qué |
|---|---|---|
| `BRAIN` | `scripted` | `scripted` o `anthropic` |
| `ANTHROPIC_API_KEY` | — | Necesaria si `BRAIN=anthropic` |
| `DEPLOY_ENABLED` | `false` | `true` para desplegar de verdad |
| `VERCEL_TOKEN` | — | Opcional; si falta usa tu sesión local |
| `ORIGENES_PERMITIDOS` | `localhost:3000` | CORS |

En el frontend, `NEXT_PUBLIC_API_URL` (por defecto `http://localhost:8000`).
