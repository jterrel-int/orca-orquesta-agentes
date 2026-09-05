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

### El problema que hay que resolver primero

Vercel solo aloja el frontend. Si lo desplegás mientras FastAPI corre en tu
laptop, el sitio en la nube apunta a `http://localhost:8000` **desde el
navegador de quien lo visite**, que no es tu máquina. El panel se ve roto: "WS
caído" y la tabla de items nunca carga. Hay tres salidas:

| Opción | Cuándo sirve | Costo |
|---|---|---|
| **Backend público** (Render/Railway/Fly) | La única en la que la URL funciona de verdad para cualquiera | Configurar un hosting más |
| **Túnel** (`cloudflared tunnel --url http://localhost:8000`) | Un demo en vivo, ahora mismo | La URL expira y depende de que tu laptop esté prendida |
| **Solo frontend** | No hay tiempo de configurar nada más | El panel muestra "WS caído" a propósito — decilo en la demo en vez de que alguien lo descubra |

Este repo usa la primera: **el backend vive en Render** (`backend/render.yaml`
ya está listo como Blueprint). Elegilo si tu caso es distinto — no hay nada
en el código que dependa de Render específicamente.

### Backend en Render

1. Conectá el repo en [render.com](https://render.com) → "New Blueprint" →
   apuntá a `backend/render.yaml`. Render crea el servicio `orquesta-backend`
   con `pip install -r requirements.txt` como build y
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT` como start.
2. Anotá la URL que te da (algo como `https://orquesta-backend.onrender.com`).
   `GET /api/health` en esa URL confirma que está vivo.
3. `ORIGENES_PERMITIDOS` queda sin completar a propósito (depende del dominio
   de Vercel, que todavía no existe) — lo llenás en el paso 5.

> La base SQLite del plan gratuito de Render es efímera: se reinicia en cada
> deploy. Suficiente para un demo; no para datos que necesiten sobrevivir un
> restart. No es un problema que este repo intente resolver.

### Frontend en Vercel

```bash
npm i -g vercel
cd frontend && vercel        # vincula el proyecto la primera vez, crea .vercel/
```

4. Configurá `NEXT_PUBLIC_API_URL` como variable de entorno de producción,
   apuntando a la URL de Render del paso 2:

   ```bash
   vercel env add NEXT_PUBLIC_API_URL production
   # pegá: https://orquesta-backend.onrender.com
   ```

   (o desde el dashboard de Vercel → Settings → Environment Variables). Como
   `NEXT_PUBLIC_*` se hornea en el build, hace falta un deploy nuevo después
   de agregarla: `vercel --prod`.

5. Volvé a Render y completá `ORIGENES_PERMITIDOS` con el dominio que Vercel
   te dio (`https://tu-proyecto.vercel.app`), sin la barra final. Sin esto el
   CORS bloquea todo. Redeployá el servicio para que tome el cambio.

6. `https://` en el frontend implica que el WebSocket tiene que ser `wss://`,
   no `ws://` — si no, el navegador lo rechaza por mixed content.
   `frontend/lib/ws.ts` expone `urlWebSocket()` justamente para esta
   conversión, y `frontend/lib/ws.test.ts` la confirma con una prueba
   (`npm run test` en `frontend/`):

   ```ts
   urlWebSocket("https://orquesta-backend.onrender.com")
   // => "wss://orquesta-backend.onrender.com/ws"
   ```

### El DeployAgent hace lo mismo que el paso 4

```bash
./scripts/deploy.sh
```

O activando el agente en `.env`:

```
DEPLOY_ENABLED=true
VERCEL_TOKEN=...     # opcional; si no, usa tu sesión local
```

El agente lanza el subproceso real, transmite su stdout línea por línea al
panel, extrae la URL de producción y falla si el código de salida no es cero
— mismo comportamiento que `vercel --prod` a mano, verificado en
`backend/tests/test_despliegue.py` con un subproceso simulado.

> El despliegue no corre dentro de Docker: el CLI de Vercel necesita tu sesión
> local. Ejecútalo en el anfitrión.

### Conectar con Vercel desde el panel (OAuth)

Además de `VERCEL_TOKEN` a mano, `/configuracion` tiene un botón **Conectar
con Vercel** que hace el login real por OAuth — mismo mecanismo que usa el MCP,
pero para que el `DeployAgent` use el token en vez de vos. Cuando hay una
conexión OAuth guardada, tiene prioridad sobre `VERCEL_TOKEN`.

Antes de que el botón funcione, tenés que registrar tu propia integración en
Vercel — es un trámite de una sola vez, en tu cuenta, y **nadie más puede
hacerlo por vos**:

1. Andá a [vercel.com/dashboard](https://vercel.com/dashboard) → elegí tu
   cuenta/team → **Integrations** → **Integrations Console** → **Create**.
2. Completá el formulario. Para uso privado (no vas a listarla en el
   marketplace) alcanza con:
   - **Name** / **URL Slug**: lo que quieras, p. ej. `orquesta-local`.
   - **Developer**, **Contact email**, **Support email**: los tuyos.
   - **Short description**, **Overview**, **Category**: cualquier texto,
     no se valida para uso privado.
   - **Logo** y **Feature media**: subí una imagen cualquiera (hasta un
     screenshot del panel sirve) — son obligatorios en el formulario aunque
     nadie más vaya a verlos.
   - **EULA URL** / **Privacy Policy URL**: podés apuntar las dos al README
     de este repo si no tenés páginas legales propias.
   - **Redirect URL**: `http://localhost:8000/api/vercel/oauth/callback`
     (Vercel acepta `localhost` explícitamente para desarrollo).
   - **API Scopes**: como mínimo `deployment` y `project` en Read/Write.
3. Guardá. Al pie de la página de tu integración vas a ver **Client ID** y
   **Client Secret** (sección **Credentials**).
4. En `backend/.env`:

   ```
   VERCEL_CLIENT_ID=...
   VERCEL_CLIENT_SECRET=...
   VERCEL_INTEGRATION_SLUG=orquesta-local   # el URL Slug del paso 2
   ```

5. Reiniciá el backend y probá el botón. Se abre una ventana emergente, te
   loguea en Vercel, y se cierra sola cuando termina.

Si en algún momento desplegás el backend a Render, agregá un **Redirect URL**
adicional apuntando a `https://tu-backend.onrender.com/api/vercel/oauth/callback`
y cambiá `VERCEL_OAUTH_REDIRECT_URI` en ese entorno.

### Conectar con Render desde el panel

Render no ofrece OAuth — su API solo se autentica con API keys personales. Por
eso `/configuracion` tiene un formulario para pegarla en vez de un botón de
login:

1. Generá una API key en Render: **Account Settings** → **API Keys**.
2. Pegala en el formulario de la sección **Render**. El backend la verifica
   contra `GET /v1/users` antes de guardarla — si no sirve, no se guarda.
3. Si existe un servicio con el nombre de `RENDER_SERVICE_NAME` (por defecto
   `orquesta-backend`, el mismo de `backend/render.yaml`), el panel muestra su
   URL y si está suspendido.

Conectar Render acá es informativo — no dispara despliegues. Render despliega
solo con cada push a la rama principal una vez que conectaste el repo desde
su dashboard (ver la sección "Backend en Render" más arriba).

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
| GET/POST | `/api/backlog` | Lee y agrega tareas a docs/BACKLOG.md |
| GET | `/api/vercel/oauth/iniciar` | Redirige a Vercel para autorizar |
| GET | `/api/vercel/oauth/callback` | Canjea el `code` y guarda el token |
| GET/DELETE | `/api/vercel/estado` / `/api/vercel/conexion` | Estado de la conexión OAuth |
| POST/GET/DELETE | `/api/render/conexion`, `/api/render/estado` | API key de Render: guardar, consultar, borrar |

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
| `VERCEL_CLIENT_ID` / `VERCEL_CLIENT_SECRET` | — | De tu integración OAuth (ver "Conectar con Vercel") |
| `VERCEL_INTEGRATION_SLUG` | — | El URL Slug que le pusiste a la integración |
| `VERCEL_OAUTH_REDIRECT_URI` | `.../api/vercel/oauth/callback` | Debe coincidir con el Redirect URL registrado |
| `RENDER_SERVICE_NAME` | `orquesta-backend` | Servicio que buscar al conectar Render |
| `ORIGENES_PERMITIDOS` | `localhost:3000` | CORS |

En el frontend, `NEXT_PUBLIC_API_URL` (por defecto `http://localhost:8000`).
