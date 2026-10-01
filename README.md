# Orquesta

Fábrica de software agéntica. Le pides algo en lenguaje natural ("crea un
gestor de tareas") y un equipo de agentes lo especifica, lo construye con sus
pruebas, lo revisa, lo verifica y lo prepara para desplegar — en paralelo
cuando se puede, frenando a preguntarte solo cuando hace falta, y dejando una
bitácora sellada de todo lo que hizo.

**Stack:** FastAPI + SQLite (async) · Next.js 15 App Router · WebSockets ·
orquestación con `asyncio` puro (Prefect opcional, solo para observar).

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

Con el cerebro guionado lanza un encargo de prueba y espera a que termine;
con un cerebro real solo revisa la salud, para no gastar cupo.

---

## El panel

| Sección | Qué tiene |
|---|---|
| **Fábrica** (`/fabrica`) | Encargar algo (o importar una especificación .pdf/.docx/.md/.txt), la lista de encargos y, en cada uno: los agentes trabajando en vivo, las especificaciones en paralelo, las decisiones pendientes, la línea de tiempo, el costo por etapa y la bitácora |
| **Ejecuciones** (`/fabrica/ejecuciones`) | Todo lo construido, desde las carpetas de `fabrica_espacios/`, agrupado por producto con su línea de versiones (v1 → v2 → …). Se exploran los archivos de cada versión, se carga un encargo archivado de vuelta en la línea, y **"Nueva versión"** crea un encargo que parte de una copia de los archivos de esa versión |
| **Salud** (`/fabrica/salud`) | Signos vitales de la fábrica, velocidad histórica, caché del LLM y plugins |
| **Configuración** (`/configuracion`) | Cerebro activo y su cuenta, conexión con Anthropic (y límite de uso), Vercel y Render |

## El cerebro

Los agentes no llaman a ninguna API: le piden contenido a su `Cerebro`. Hay
cuatro implementaciones tras el mismo protocolo, elegidas con `BRAIN` en
`backend/.env`:

- `scripted` — determinista, sin red, sin clave. **Por defecto.** Sirve para
  ver el flujo completo gratis; el código que produce es una plantilla.
- `anthropic` — la API de mensajes de Anthropic (se factura por token). Con
  `ANTHROPIC_API_KEY` o conectando la clave desde Configuración.
- `claude-cli` — corre `claude -p` como subproceso, con el CLI de Claude Code
  ya logueado en esta máquina. **Solo para desarrollo local**: consume el cupo
  de tu plan (sesión de 5 horas, cupo semanal), no funciona en un backend
  desplegado, y usar la suscripción como backend de otra app es una zona gris
  de sus términos de uso — es una decisión de quien lo activa.
- `openai-compatible` — cualquier API con el formato de chat completions de
  OpenAI; DeepSeek por defecto.

Si la llamada falla, el cerebro cae al respaldo determinista en vez de tumbar
el encargo — y la bitácora dice `origen: plantilla`, así se nota.

---

## Fábrica de software (`/fabrica`)

Además del demo de tres agentes, Orquesta tiene un pipeline completo que
lleva un pedido en lenguaje natural hasta un PR, con la mínima intervención
humana posible y todo medido.

```
pedido → Especificador → por cada especificación, en orden de dependencias:
           Implementador → Revisor ─rechazo→ Diagnosticador (efímero)
                              │                ├ implementación → reintento
                              │                ├ especificación → pregunta a una persona
                              │                └ harness → bloqueada, sin reintentar
                              └ aprobado → Verificador → compuerta de plugins → aprobada
         (las especificaciones independientes entre sí recorren esto en paralelo)
       → Despliegue (PR + GitHub Actions) cuando todas quedaron aprobadas
```

| Agente | Qué hace | Dónde |
|---|---|---|
| **Líder** | Orden, reintentos, presupuesto, pausas humanas | `orchestrator/lider.py` |
| **Especificador** | Parte el pedido en especificaciones con dependencias y marca cuáles necesitan aprobación. Pregunta cuando algo es ambiguo, p. ej. un pedido que choca con una **tabla legada** que ya existe en la base | `agents/fabrica/especificador.py` |
| **Implementador** | Todo: código, interfaz y pruebas unitarias. Sin roles separados de front y back | `agents/fabrica/implementador.py` |
| **Revisor** | Valida contra la especificación y **corre pytest de verdad** | `agents/fabrica/revisor.py` |
| **Diagnosticador** | Solo existe si el Revisor rechaza: ¿falló el código, la especificación o el entorno? | `agents/fabrica/diagnosticador.py` |
| **Verificador** | Caja blanca (cada función pública tiene una prueba, leído del AST) y Playwright con Chromium en un contenedor | `agents/fabrica/verificador.py` |
| **Despliegue** | Escribe `.github/workflows/ci.yml`, abre la rama y el PR | `agents/fabrica/despliegue.py` |

### Los principios, y dónde se cumplen

- **Determinismo.** La IA propone; las reglas deciden. Las rutas que un
  agente puede escribir, los comandos que se pueden correr, el orden de las
  dependencias y los criterios de aprobación son código, no prompt
  (`dominio/fabrica.py`). El LLM puede *rechazar* algo que las reglas
  aprobaron, nunca *aprobar* algo que rechazaron. Con el cerebro guionado,
  todo el pipeline corre sin API key y da siempre el mismo resultado.
- **Bitácora inmutable.** Registra lo que *pasó*, no lo que el agente dice:
  hashes de los archivos releídos del disco y códigos de salida reales. Cada
  registro lleva el hash del anterior, así que alterar uno rompe la cadena
  desde ahí, y SQLite rechaza `UPDATE` y `DELETE` sobre la tabla con un
  trigger. El Revisor hace **validación cruzada**: si un archivo no coincide
  con el hash que registró el Implementador, rechaza.
- **Costo y tiempo por etapa.** Cada etapa guarda modelo, tokens, USD y
  segundos (`fabrica_metricas`). La página `/fabrica/salud` arma con eso la
  **velocidad histórica** de la fábrica.
- **Mínima intervención humana.** `FABRICA_APROBACION_HUMANA=ambiguedad` (por
  defecto) solo frena ante una ambigüedad real o una especificación riesgosa
  (borrado, pagos, permisos, producción). `nunca` decide solo, pero deja cada
  decisión en la bitácora. `siempre` pide aprobación para todo.
- **Confianza por diseño.** En vez de frenar cada encargo, `/fabrica/salud`
  vigila signos vitales al estilo de una UCI: volumen, tasa de aprobación al
  primer intento, rechazos por causa, costo contra presupuesto, encargos
  esperando a una persona e integridad de la bitácora, con alertas.
- **Modelos más baratos.** Modelo por rol (`FABRICA_MODELO_*`) y un proveedor
  compatible con OpenAI (`BRAIN=openai-compatible`, DeepSeek por defecto).
  Como el harness valida todo, el Especificador, el Revisor y el
  Diagnosticador pueden correr en un modelo chico.

### Paralelismo

Las especificaciones que no dependen entre sí se construyen **a la vez**. El
Líder trabaja por tandas: todo lo que tiene sus dependencias aprobadas entra
a la tanda y corre con `asyncio.gather`, con un tope de `FABRICA_PARALELISMO`
(3 por defecto). Al terminar una tanda se destraba la siguiente. Una
especificación que espera aprobación humana no frena a sus hermanas: se
construyen las demás y el encargo se pausa recién cuando no queda otra cosa
por hacer. Además, cada encargo corre en su propia tarea, así que varios
pedidos avanzan en paralelo.

El Especificador heurístico toma la primera funcionalidad como base y hace
depender el resto solo de ella, así que S2…Sn corren en paralelo. Con un LLM,
se le pide que declare solo las dependencias reales. Si dos especificaciones
paralelas tocaran el mismo archivo, la validación cruzada del Revisor lo
detecta: el hash registrado ya no coincide con el disco.

En el panel, `/fabrica/<id>` muestra los carriles por nivel ("Nivel 2 · 5 en
paralelo"), cuántas instancias de cada agente trabajan a la vez y una línea
de tiempo con la duración real de cada etapa, donde se ve el solapamiento.
También muestra la concurrencia máxima alcanzada y el ahorro contra hacerlo
todo en fila.

### Prefect (opcional)

```bash
pip install -r backend/requirements-prefect.txt
prefect server start          # UI en http://127.0.0.1:4200
# en .env: FABRICA_ORQUESTADOR=prefect
```

Cada encargo aparece como un *flow run* (`encargo-<id>`) y cada etapa como un
*task run* (`S2-revision-1`, …), con estado y duración. Prefect **observa**:
el orden, los reintentos y el paralelismo los sigue decidiendo el Líder con
asyncio, así que apagarlo no cambia ningún resultado. Sin el paquete
instalado, la fábrica corre igual y `/api/health` lo avisa.
`requirements-prefect.txt` sube `pydantic-settings`: la versión fijada en
`requirements.txt` no es compatible con Prefect 3.

### Caché, plugins y compactación de contexto

- **Caché de respuestas del LLM** (`FABRICA_CACHE_LLM=true`,
  `adaptadores/cache_llm.py`): un prompt idéntico (mismo modelo, instrucción y
  contexto) no se paga dos veces, lo que ayuda en reintentos y al reanudar. Un
  acierto no cuenta como gasto; el ahorro se informa aparte en
  `GET /api/fabrica/cache`. Nunca se cachea un respaldo por fallo. Está
  apagada por defecto porque fija la primera respuesta en vez de muestrear
  una nueva.
- **Plugins** (`orchestrator/plugins.py`, archivos en `backend/plugins/`):
  ganchos en `encargo_creado`, `especificaciones_listas`, `rechazo`,
  `especificacion_aprobada`, `especificacion_fallida` y `encargo_terminado`,
  más la compuerta `antes_de_aprobar`, que puede vetar. Un veto entra al
  ciclo de reintentos como un rechazo más. Un plugin que falla no tumba el
  encargo; una compuerta que falla cuenta como veto. Hay un ejemplo
  desactivado, `_ejemplo_prohibir_eval.py`: renómbralo sin el `_` para
  activarlo.
- **Compactación de contexto** (`agents/fabrica/comun.py::armar_contexto`):
  si el contexto de una etapa supera `FABRICA_LIMITE_CONTEXTO` caracteres, se
  recorta por el centro el texto más largo hasta que entra. Es determinista
  (no la resume un LLM, que podría inventar), así que la caché sigue
  acertando. Cada reintento recibe además un resumen compacto de los
  intentos anteriores.

### Dónde corre el código generado

Cada encargo trabaja en `fabrica_espacios/<id>/` (ignorado por git) y solo
puede escribir en `src/`, `tests/`, `frontend/` y `e2e/`. Las pruebas corren:

- `FABRICA_SANDBOX=local` (por defecto): subproceso, sin ninguna variable
  `*_API_KEY`/`*TOKEN*`/`*SECRET*` en el entorno.
- `FABRICA_SANDBOX=docker`: contenedor sin red, raíz de solo lectura y sin
  capacidades. **Úsalo con un cerebro real**; `/api/health` te lo recuerda.
  Imagen: `docker build -f backend/sandbox.Dockerfile -t orquesta-sandbox:latest backend`.

Playwright (`FABRICA_E2E_ENABLED=true`) corre en
`mcr.microsoft.com/playwright` contra `FABRICA_E2E_URL_BASE`. Apagado, la
verificación funcional figura como **omitida**, no como aprobada. El
despliegue sigue la regla de siempre: con `DEPLOY_ENABLED=false` solo informa
los comandos `git`/`gh` que correría.

### API

| Método | Ruta | |
|---|---|---|
| POST | `/api/fabrica/encargos` | `{pedido}` → 202, arranca en segundo plano |
| GET | `/api/fabrica/encargos[/{id}]` | Estado, especificaciones, preguntas y costo |
| POST | `/api/fabrica/encargos/{id}/preguntas/{pid}` | `{respuesta}` |
| POST | `/api/fabrica/encargos/{id}/especificaciones/{sid}/aprobar` · `/rechazar` | Compuerta humana |
| POST | `/api/fabrica/encargos/{id}/reanudar` | Tras un reinicio o un fallo |
| GET | `/api/fabrica/encargos/{id}/bitacora` · `/metricas` | Evidencia y costo por etapa |
| GET | `/api/fabrica/salud` | Signos vitales y velocidad |
| GET/POST | `/api/fabrica/cache` · `/cache/limpiar` | Caché de respuestas |
| GET | `/api/fabrica/plugins` | Plugins cargados y errores |
| POST | `/api/fabrica/encargos` con `base_id` | Nueva versión: copia los archivos de ese encargo y especifica solo el cambio |
| POST | `/api/fabrica/linea/reiniciar` | Detiene lo que corre y archiva los encargos de la línea. No borra nada |
| GET | `/api/fabrica/ejecuciones` | Carpetas de `fabrica_espacios/` cruzadas con sus encargos |
| GET | `/api/fabrica/ejecuciones/{id}/archivos` · `/archivo?ruta=` | Archivos de una ejecución, solo lectura y sin salir de su carpeta |
| GET | `/api/fabrica/config` | Paralelismo, orquestador y políticas activas |

El progreso en vivo viaja por `/ws` con el contrato de siempre, con
`run_id` = id del encargo.

---

## Desplegar Orquesta (Vercel + Render)

Cómo publicar Orquesta misma: el frontend en Vercel y el backend en Render.
Es un paso manual, a propósito; no lo hace ningún agente.

### El problema que hay que resolver primero

Vercel solo aloja el frontend. Si lo desplegás mientras FastAPI corre en tu
laptop, el sitio en la nube apunta a `http://localhost:8000` **desde el
navegador de quien lo visite**, que no es tu máquina. El panel se ve roto: "WS
caído" y la lista de encargos nunca carga. Hay tres salidas:

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

### Desplegar el frontend desde tu máquina

```bash
./scripts/deploy.sh
```

Corre `vercel --prod` en `frontend/`. No corre dentro de Docker: el CLI de
Vercel necesita tu sesión local. Esto despliega **Orquesta**; lo que construye
cada encargo de la fábrica se publica por otro camino (PR a GitHub, ver
"Dónde corre el código generado").

### Conectar con Vercel desde el panel (OAuth)

Además de `VERCEL_TOKEN` a mano, `/configuracion` tiene un botón **Conectar
con Vercel** que hace el login real por OAuth — mismo mecanismo que usa el MCP.
Hoy la conexión es informativa: ningún agente despliega a Vercel (la etapa de
Despliegue de la fábrica publica en GitHub).

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
  hace el CLI (`vercel --prod`, con `./scripts/deploy.sh`). No hay
  código en este repo que espere desplegar a través del MCP.

Verificá que quedó andando con `claude mcp list` o `/mcp` dentro de una
sesión.

---

## API

La de la fábrica está en su sección ("API", más arriba). Además:

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/health` | Salud, cerebro activo y su cuenta, advertencias de configuración |
| WS | `/ws` | Stream de eventos en vivo (reenvía el historial al conectar) |
| GET/POST/DELETE | `/api/anthropic/…` | API key de Anthropic y límite local de uso |
| GET | `/api/vercel/oauth/iniciar` | Redirige a Vercel para autorizar |
| GET | `/api/vercel/oauth/callback` | Canjea el `code` y guarda el token |
| GET/DELETE | `/api/vercel/estado` / `/api/vercel/conexion` | Estado de la conexión OAuth |
| POST/GET/DELETE | `/api/render/conexion`, `/api/render/estado` | API key de Render: guardar, consultar, borrar |

Formato de los eventos:

```json
{ "agent": "implementador", "status": "running", "msg": "S2 · intento 1/2: …", "ts": "…", "run_id": "<id del encargo>", "artifacts": [] }
```

`agent`, `status` y `msg` son los tres campos del contrato; el resto es opcional
y un cliente antiguo puede ignorarlos.

---

## Decisiones que quizá te sorprendan

**El despliegue automático está apagado.** Con `DEPLOY_ENABLED=false` la
etapa de Despliegue informa los comandos `git`/`gh` que correría y no publica
nada. Un agente que publica sin que una persona lo pida es un incidente
esperando a ocurrir. Está implementado de verdad, con un flag para activarlo.

**El cerebro por defecto es determinista.** Un demo en vivo no debería depender
de una clave de API ni de que la red aguante. `BRAIN` lo cambia.

**El WebSocket reenvía su historial al conectar.** Una pestaña abierta a mitad
de un encargo no se queda mirando una pantalla vacía.

**Un único consumidor del bus retransmite a todos los clientes**, en vez de una
suscripción por pestaña. El bus no crece con el número de pestañas abiertas.

**No se usa `next/font/google`.** Descarga las fuentes durante el build y lo
hace fallar sin red. Con `<link>`, sin conexión cae al stack del sistema.

---

## Variables de entorno

Copia `.env.example` a `.env`. Ninguna es obligatoria.

| Variable | Por defecto | Para qué |
|---|---|---|
| `BRAIN` | `scripted` | `scripted`, `anthropic`, `claude-cli` u `openai-compatible` |
| `ANTHROPIC_API_KEY` | — | Necesaria si `BRAIN=anthropic` |
| `CLAUDE_CLI_COMANDO` | `claude` | Binario a invocar si `BRAIN=claude-cli` |
| `CLAUDE_CLI_TIMEOUT_S` | `300` | Segundos antes de caer al respaldo si `BRAIN=claude-cli`. Una especificación grande puede necesitar más |
| `DEPLOY_ENABLED` | `false` | `true` para que la fábrica abra PRs reales (con `GITHUB_REPO`) |
| `FABRICA_*` | ver `.env.example` | Paralelismo, reintentos, presupuesto, aprobación humana, sandbox, caché, Prefect |
| `VERCEL_TOKEN` | — | Opcional; alternativa a conectar Vercel desde Configuración |
| `VERCEL_CLIENT_ID` / `VERCEL_CLIENT_SECRET` | — | De tu integración OAuth (ver "Conectar con Vercel") |
| `VERCEL_INTEGRATION_SLUG` | — | El URL Slug que le pusiste a la integración |
| `VERCEL_OAUTH_REDIRECT_URI` | `.../api/vercel/oauth/callback` | Debe coincidir con el Redirect URL registrado |
| `RENDER_SERVICE_NAME` | `orquesta-backend` | Servicio que buscar al conectar Render |
| `ORIGENES_PERMITIDOS` | `localhost:3000` | CORS |

En el frontend, `NEXT_PUBLIC_API_URL` (por defecto `http://localhost:8000`).
