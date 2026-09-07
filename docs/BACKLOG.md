# Backlog

Cada tarea toca un solo lado (backend o frontend) y está pensada para una
sesión de agente. `Depende de` marca cuándo una tarea FE necesita que una BE
ya esté fusionada — no las lances en paralelo si hay una dependencia sin
resolver.

---

## BE-01 — TestAgent: cuarta etapa del pipeline

Un agente nuevo que corre `pytest -q` sobre `backend/tests/` como parte de la
corrida, entre el backend/frontend y el deploy. Si las pruebas fallan, el
deploy se omite — mismo mecanismo que ya existe para cualquier fallo de etapa.

**Archivos:** `backend/app/agents/test_agent.py` (nuevo),
`backend/app/agents/__init__.py`, `backend/app/orchestrator/orquestador.py`
(agregar `[TestAgent()]` como etapa entre `[BackendAgent(), FrontendAgent()]`
y `[DeployAgent()]`).

**Verificación:** `pytest -q` sobre un `test_agentes.py` ampliado que
verifique que un `TestAgent` con un subproceso simulado que falla marca
`status="error"`; `curl -X POST /api/run` seguido de `/api/run/status` muestra
cuatro agentes, no tres.

**Depende de:** nada.

---

## BE-02 — Persistir el historial de corridas en SQLite

Hoy el historial de eventos vive solo en memoria (`BusEventosMemoria`) y se
pierde al reiniciar. Agregar una tabla `corridas` (run_id, status,
iniciado_en, terminado_en) y un endpoint `GET /api/run/historial` que liste
las últimas N corridas.

**Archivos:** `backend/app/dominio/puertos.py` (puerto `RepositorioCorridas`),
`backend/app/adaptadores/persistencia_sqlalchemy.py` (ORM + implementación),
`backend/app/orchestrator/orquestador.py` (persistir al terminar),
`backend/app/api/corridas.py` (nuevo endpoint).

**Verificación:** `pytest -q` sobre un `test_historial_corridas.py` nuevo
(SQLite en memoria, igual que `test_items.py`); tras dos `POST /api/run`
seguidos, `GET /api/run/historial` devuelve dos entradas en orden.

**Depende de:** nada. FE-03 depende de esta.

---

## BE-03 — Cancelar una corrida en curso

`DELETE /api/run` cancela la corrida activa: cancela la `asyncio.Task` del
orquestador, marca los agentes que no llegaron a terminar como `error` con
mensaje "cancelado", y libera el lock para que se pueda lanzar otra.

**Archivos:** `backend/app/orchestrator/orquestador.py` (guardar la `Task` y
exponer `cancelar()`), `backend/app/api/corridas.py` (endpoint `DELETE
/api/run`).

**Verificación:** `pytest -q` sobre `test_orquestador.py` ampliado (cancelar a
mitad de una etapa dos dejo el resto en `error`); manualmente, lanzar
`POST /api/run` y en el segundo siguiente `DELETE /api/run` corta la corrida.

**Depende de:** nada.

---

## BE-04 — DocsAgent: resumen en markdown de la corrida

Un agente nuevo que, al terminar el pipeline, escribe
`docs/corridas/<run_id>.md` con qué agentes corrieron, cuánto tardaron, qué
archivos generaron y la URL de despliegue si la hubo.

**Archivos:** `backend/app/agents/docs_agent.py` (nuevo),
`backend/app/agents/__init__.py`, `backend/app/orchestrator/orquestador.py`
(agregarlo como última etapa, después de deploy).

**Verificación:** `pytest -q` sobre `test_agentes.py` ampliado (verifica que
el markdown generado contiene los nombres de los agentes y sus duraciones);
tras `POST /api/run`, existe `docs/corridas/<run_id>.md` con contenido no
vacío.

**Depende de:** nada.

---

## FE-01 — Filtro de logs por agente

En el panel, un selector (o botones) sobre `LogStream` para mostrar solo los
eventos de `backend`, `frontend`, `deploy` u `orchestrator`, o todos.

**Archivos:** `frontend/components/LogStream.tsx`, `frontend/app/page.tsx` (si
hace falta levantar el estado del filtro).

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, correr el
panel, lanzar una corrida y confirmar que el filtro oculta/muestra logs por
agente sin perder eventos al cambiar de filtro.

**Depende de:** nada.

---

## FE-02 — Botón de descarga de logs

Un botón en el panel que descarga los eventos visibles como `.json` (o
`.txt`, una línea por evento). Es client-side puro: arma un `Blob` a partir
del arreglo de eventos que ya tiene `useEventos`, sin tocar el backend.

**Archivos:** `frontend/components/LogStream.tsx` (o un componente nuevo
`DescargarLogs.tsx`), `frontend/lib/types.ts` si hace falta un tipo para el
formato exportado.

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, confirmar
que el archivo descargado contiene los eventos mostrados en pantalla.

**Depende de:** nada.

---

## FE-03 — Histórico de corridas anteriores

Una vista (`/historial` o una sección del panel) que lista corridas pasadas
usando el endpoint de BE-02.

**Archivos:** `frontend/lib/api.ts` (función `historialCorridas`),
`frontend/lib/types.ts` (tipo para una entrada del historial),
`frontend/app/historial/page.tsx` (nuevo).

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, con al
menos dos corridas ya hechas, `/historial` las lista con su estado y horario.

**Depende de:** BE-02 (necesita `GET /api/run/historial`).

---

## BE-05 — Parametrizar el pipeline por caso de uso

Hoy `Orquestador.ejecutar()` no recibe parámetros y `BackendAgent`/
`FrontendAgent` tienen hardcodeados el `INSTRUCCION` y el `respaldo` del CRUD
de "Item". Se necesita poder lanzar 3 corridas de demo distintas
(calculadora, leads de zapatillas, encuesta) además de la de Items, sin
duplicar el pipeline.

Crear `backend/app/agents/casos_de_uso.py` con: (1) un `CasoDeUso` (id,
nombre, descripcion, icono) por cada caso más "items", para exponer metadata
al frontend; (2) un registro interno por caso con instrucción para el
cerebro, contexto, código de respaldo, prefijo de rutas API, nombre del
archivo generado en backend y nombre/ruta del componente generado en
frontend. `None`/`"items"` debe mapear exactamente a las constantes actuales
(`INSTRUCCION`, `ROUTER_ITEMS`, `LISTA_ITEMS_TSX`) — no reescribirlas, solo
moverlas al registro.

`Orquestador.ejecutar(caso_de_uso: str | None = None)` mete el valor en
`ContextoCorrida.datos["caso_de_uso"]` y en `self._resumen.caso_de_uso`
(campo nuevo en `ResumenCorrida`, que no es el contrato congelado del
WebSocket — `EventoAgente` no se toca). `BackendAgent`/`FrontendAgent` leen
`ctx.datos.get("caso_de_uso")` y usan el registro en vez de las constantes
fijas. `POST /api/run` acepta un body opcional `{"caso_de_uso": "..." |
null}`; ausente o `null` es el comportamiento de hoy. Nuevo endpoint `GET
/api/casos-de-uso` que devuelve la lista de `CasoDeUso` para que el frontend
no hardcodee esa metadata.

`main.py:montar_router_generado` deja de estar cableado a un único
`item_routes.py`: itera los (archivo, nombre de módulo) de todos los casos
con código generado y monta los que existan — cada caso tiene su propio
prefijo de API, así que no colisionan al convivir montados.

**Archivos:** `backend/app/agents/casos_de_uso.py` (nuevo),
`backend/app/agents/backend_agent.py`, `backend/app/agents/frontend_agent.py`,
`backend/app/orchestrator/orquestador.py`, `backend/app/dominio/modelos.py`
(`ResumenCorrida.caso_de_uso`), `backend/app/api/corridas.py` (body de
`POST /api/run`, nuevo `GET /api/casos-de-uso`), `backend/app/main.py`
(`montar_router_generado` iterando varios casos), `backend/app/config.py` si
hace falta generalizar `dir_generado_backend`.

**Verificación:** `ruff check . && ruff format --check .`, `mypy
app/dominio`, `pytest -q` (`test_arquitectura.py` en verde: nada de esto
importa `fastapi`/`sqlalchemy` desde `dominio/`); ampliar
`test_agentes.py`/`test_orquestador.py` para cubrir que `caso_de_uso=None`
sigue generando el CRUD de Item byte a byte igual que antes, y que pasar
`"calculadora"` selecciona la instrucción/respaldo correctos.

**Depende de:** nada. BE-06, BE-07, BE-08 y todo FE-06..FE-09 dependen de
esta.

---

## BE-06 — Caso de uso "Calculadora con login e historial"

Router FastAPI autocontenido en `/api/calculadora`, montado dinámicamente
igual que el de Items. Reutiliza `motor`/`FabricaSesion` de
`persistencia_sqlalchemy.py` (tablas propias: usuarios, sesiones,
operaciones). Endpoints: `POST /registro` (usuario, clave — hashea con
`hashlib.pbkdf2_hmac` + `secrets.token_hex` para el salt, 409 si el usuario
ya existe), `POST /login` (valida y devuelve un token de sesión guardado en
tabla propia), `POST /operar` (autenticado con `Authorization: Bearer
<token>`; +,-,*,/ con división por cero controlada; persiste cada operación
con el id del usuario), `GET /historial` (autenticado, lista las operaciones
del usuario logueado, más recientes primero). Este es el código de
`respaldo` para `caso_de_uso="calculadora"` que registra BE-05.

**Archivos:** `backend/app/agents/plantillas_calculadora.py` (o sección
dedicada en `plantillas.py`), enganchado desde el registro de BE-05.

**Verificación:** `pytest -q` sobre un `test_caso_calculadora.py` nuevo
(SQLite en memoria): registro → login → operar → historial devuelve la
operación; login con clave incorrecta da 401; `/operar` sin token da 401;
`ruff`/`mypy` en verde.

**Depende de:** BE-05.

---

## BE-07 — Caso de uso "Leads de zapatillas"

Router FastAPI autocontenido en `/api/leads`. Tabla propia (nombre, email,
teléfono, talla, comentario, creado_en). `POST /` guarda un lead (validación
básica: nombre y email no vacíos, email con formato mínimo); `GET /` lista
los leads capturados, más recientes primero. Sin autenticación — es una
demo pública, se documenta como tal en el código. Este es el `respaldo` para
`caso_de_uso="leads_zapatillas"`.

**Archivos:** `backend/app/agents/plantillas_leads.py` (o sección dedicada
en `plantillas.py`), enganchado desde el registro de BE-05.

**Verificación:** `pytest -q` sobre `test_caso_leads.py` nuevo: `POST /`
seguido de `GET /` devuelve el lead creado; `POST /` con email vacío da 422;
`ruff`/`mypy` en verde.

**Depende de:** BE-05.

---

## BE-08 — Caso de uso "Encuesta de satisfacción"

Router FastAPI autocontenido en `/api/encuesta`. Tabla propia (puntaje 1-5,
comentario opcional, creado_en). `POST /` guarda una respuesta (rechaza
puntaje fuera de 1-5); `GET /resultados` devuelve total de respuestas,
promedio y conteo por puntaje (1..5). Este es el `respaldo` para
`caso_de_uso="encuesta"`.

**Archivos:** `backend/app/agents/plantillas_encuesta.py` (o sección
dedicada en `plantillas.py`), enganchado desde el registro de BE-05.

**Verificación:** `pytest -q` sobre `test_caso_encuesta.py` nuevo: varias
`POST /` seguidas de `GET /resultados` devuelven el promedio y el conteo
correctos; puntaje 0 o 6 da 422; `ruff`/`mypy` en verde.

**Depende de:** BE-05.

---

## FE-04 — Rediseño de paleta, logo y Sidebar

Reemplazar el tema oscuro actual por uno claro inspirado en el logo de
inteligenze (azul petróleo `#0B3A4D` sobre blanco). Actualizar los tokens de
color en `frontend/app/globals.css` (`--marca`, `--fondo`, `--panel`,
`--borde`, `--texto`, `--backend`/`--frontend`/`--deploy`, etc. — ver el
plan de diseño), subir `--radio` para cards más redondeadas, y agregar una
fuente serif solo para títulos/el lockup del logo. Ninguna clase utilitaria
existente cambia de nombre ni de estructura, solo sus valores.

Agregar el logo (`frontend/public/logo-inteligenze.webp`) arriba del nav en
`Sidebar.tsx`.

**Archivos:** `frontend/app/globals.css`, `frontend/components/Sidebar.tsx`,
`frontend/public/logo-inteligenze.webp` (nuevo asset).

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, levantar
el panel y confirmar que todas las páginas (Panel, Items, Backlog,
Configuración) se ven legibles con el nuevo tema — sin texto sobre fondo del
mismo color, sin contraste roto en los estados `error`/`ok`/`advertencia`.

**Depende de:** nada.

---

## FE-05 — Backlog con tabs por frente y cards rediseñadas

En `frontend/app/backlog/page.tsx`, agregar tabs ("Todas" / "Backend" /
"Frontend") que filtran `tareas` client-side por `t.lado` — el dato ya viene
de `GET /api/backlog`, no hace falta tocar el backend. Restylear
`tarjeta-tarea`: acento de color por lado, mejor jerarquía tipográfica del
título, y separar visualmente dentro de `cuerpo-tarea` las subsecciones que
ya trae el markdown (Archivos/Verificación/Depende de) partiendo el string
por esos encabezados en el componente.

**Archivos:** `frontend/app/backlog/page.tsx`, `frontend/app/globals.css`
(estilos de `tarjeta-tarea` y de las tabs nuevas).

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, con
tareas BE y FE existentes, confirmar que cada tab filtra correctamente y que
las subsecciones de cada card se leen separadas.

**Depende de:** FE-04 (usa los tokens de color nuevos).

---

## FE-06 — Panel: sección "Casos de prueba" + rediseño de tarjetas

Restylear `AgentCard` (ícono simple por rol, acento de color, sombra suave)
y `LogStream` (de consola oscura a feed de actividad sobre fondo claro,
borde de color por agente). Agregar una sección nueva "Casos de prueba" en
`frontend/app/page.tsx` con 3 cards (una por caso de BE-06/07/08), cuya
metadata viene de un nuevo `GET /api/casos-de-uso` (función `casosDeUso()`
en `frontend/lib/api.ts`) — no hardcodear nombres/descripciones en el
componente. Cada card tiene un botón "Ejecutar" que llama a
`lanzarCorrida(casoDeUsoId)` (ampliar `lanzarCorrida` en `lib/api.ts` para
mandar el body `{caso_de_uso}`) y, cuando el `ResumenCorrida.caso_de_uso`
coincide y `status === "done"`, un link "Ver resultado" a su página
(`ruta_frontend` de la metadata). El botón "Ejecutar agentes" genérico
(Items) se mantiene, más chico, como cuarta opción.

**Archivos:** `frontend/app/page.tsx`, `frontend/components/AgentCard.tsx`,
`frontend/components/LogStream.tsx`, `frontend/components/RunButton.tsx`
(o un componente nuevo `CasoDePruebaCard.tsx`), `frontend/lib/api.ts`,
`frontend/lib/types.ts` (`CasoDeUso`, `ResumenCorrida.caso_de_uso`),
`frontend/app/globals.css`.

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, con el
backend de BE-05 corriendo, lanzar cada uno de los 3 casos desde su card y
confirmar que las `AgentCard` y el `LogStream` muestran el progreso real, y
que "Ver resultado" aparece al terminar.

**Depende de:** FE-04, BE-05.

---

## FE-07 — Página del caso "Calculadora"

Shell de página `frontend/app/casos/calculadora/page.tsx` (mismo patrón que
`app/items/page.tsx`) que importa un componente `Calculadora.tsx` cuyo
*contenido* es lo que sobreescribe el `FrontendAgent` en cada corrida de
este caso. El archivo inicial ya trae el código de respaldo (igual que
`ListaItems.tsx` hoy) para que la página funcione antes de correr el agente:
login/registro → teclado de calculadora → tabla de historial → cerrar
sesión. Token de sesión en `localStorage`.

**Archivos:** `frontend/app/casos/calculadora/page.tsx` (nuevo),
`frontend/app/casos/calculadora/Calculadora.tsx` (nuevo, contenido inicial =
respaldo), `frontend/lib/api.ts` (helpers para `/api/calculadora/*`).

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, registrar
un usuario, loguearse, hacer una operación y ver que aparece en el
historial; cerrar sesión y confirmar que pide login de nuevo.

**Depende de:** BE-06.

---

## FE-08 — Página del caso "Leads de zapatillas"

Shell de página `frontend/app/casos/leads/page.tsx` que importa
`FormularioLeads.tsx` (contenido inicial = respaldo): formulario público
(nombre, email, teléfono, talla, comentario) con validación básica y
confirmación visual al enviar, más una tabla debajo con los leads ya
capturados (`GET /api/leads`).

**Archivos:** `frontend/app/casos/leads/page.tsx` (nuevo),
`frontend/app/casos/leads/FormularioLeads.tsx` (nuevo), `frontend/lib/api.ts`
(helpers para `/api/leads`).

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, enviar un
lead y confirmar que aparece en la tabla sin recargar la página.

**Depende de:** BE-07.

---

## FE-09 — Página del caso "Encuesta"

Shell de página `frontend/app/casos/encuesta/page.tsx` que importa
`Encuesta.tsx` (contenido inicial = respaldo): selector de puntaje 1-5 +
comentario opcional, y una sección de resultados agregados (barras hechas
con `div`+CSS, sin librería de gráficos) usando `GET /api/encuesta/resultados`.

**Archivos:** `frontend/app/casos/encuesta/page.tsx` (nuevo),
`frontend/app/casos/encuesta/Encuesta.tsx` (nuevo), `frontend/lib/api.ts`
(helpers para `/api/encuesta`).

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, enviar
varias respuestas y confirmar que el promedio y el conteo por puntaje se
actualizan.

**Depende de:** BE-08.

---

## BE-09 — `.gitignore` incompleto para los routers generados de los casos nuevos

`.gitignore` solo ignora `backend/app/generated/item_routes.py`. Los routers
que escribe `BackendAgent` para los tres casos de BE-06/07/08
(`calculadora_routes.py`, `leads_routes.py`, `encuesta_routes.py`) no están
listados, así que después de correr cualquiera de esos casos quedan como
archivos sin trackear en `git status` — confirmado corriendo los 3 casos en
la verificación post-merge del 2026-09-06 (ver `docs/BITACORA.md`).

**Archivos:** `.gitignore` (agregar los tres archivos, o cambiar a un patrón
que cubra cualquier archivo nuevo en `backend/app/generated/` salvo
`.gitkeep`/`__init__.py` — así no hace falta tocarlo de nuevo si se agrega un
quinto caso de uso).

**Verificación:** lanzar los 4 casos (`items`, `calculadora`,
`leads_zapatillas`, `encuesta`) con `POST /api/run` y confirmar con `git
status --short` que `backend/app/generated/` no aparece con archivos sin
trackear.

**Depende de:** nada.

---

## BE-10 — `montar_router_generado` remonta todos los casos en cada corrida, no solo el nuevo

`main.py:_post_corrida` llama `montar_router_generado(app)` al terminar
cualquier corrida, y esa función recorre `archivos_backend_generados()`
completo — todos los casos que alguna vez se generaron y siguen en disco,
no solo el que acaba de correr — y vuelve a hacer
`app.include_router(...)` sobre cada uno. Confirmado en los logs de una
sesión real: tras la corrida de "leads" se remontaron `item_routes.py`,
`calculadora_routes.py` y `leads_routes.py` los tres, cuando solo
`leads_routes.py` era nuevo. Cada remontaje reimporta el módulo bajo un
`spec` nuevo, lo que dispara `SAWarning` de SQLAlchemy por cada clase ORM
del caso (ya visible en `pytest -q`, 23 warnings) y deja objetos `Route`
duplicados acumulándose en `app.routes` para el mismo path dentro del mismo
proceso de larga duración. No rompe nada hoy (`extend_existing=True` evita
que explote, y los endpoints responden igual), pero es un desperdicio que
crece sin límite mientras el proceso siga vivo.

Alternativa a evaluar: que `montar_router_generado` lleve un registro de
qué módulos ya están montados en esa instancia de `app` (por ejemplo, un
`set` de nombres de archivo en `app.state`) y salte los que ya estén, en vez
de recorrer y remontar todo cada vez.

**Archivos:** `backend/app/main.py` (`montar_router_generado`,
`_post_corrida`), `backend/tests/test_montaje_generado.py` (ampliar para
afirmar que un segundo llamado no duplica rutas en `app.routes`, no solo que
"no explota").

**Verificación:** `pytest -q` con el test ampliado en verde; manualmente,
lanzar dos corridas seguidas de casos distintos y confirmar (contando
`app.routes` o revisando los logs) que cada archivo se monta una sola vez
por proceso.

**Depende de:** nada.

---

## FE-10 — Distinguir visualmente la opción "Items" en "Casos de prueba"

FE-06 pedía que el botón "Ejecutar agentes" genérico (Items) se mantuviera
"más chico, como cuarta opción" dentro de la sección "Casos de prueba". La
implementación actual (`CasoDePruebaCard`) renderiza las 4 opciones con el
mismo tamaño y markup — funciona igual que las demás pero no hay diferencia
visual que la marque como la opción "clásica"/de respaldo frente a los 3
casos de demo nuevos.

**Archivos:** `frontend/app/page.tsx` (cómo se renderiza la card de
`items` dentro de `rejilla-casos`), `frontend/components/CasoDePruebaCard.tsx`
(o una variante/prop `chico`), `frontend/app/globals.css`.

**Verificación:** `npx tsc --noEmit`, `npm run build`; manualmente, en el
Panel, confirmar que la tarjeta de Items se distingue visualmente (tamaño o
jerarquía) de las 3 tarjetas de casos de demo, sin perder funcionalidad.

**Depende de:** FE-06 (ya fusionada).
