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
