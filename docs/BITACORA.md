# Bitácora

Registro de cada corrida de verificación completa en `master`, hecha por el
agente `revisor` después de fusionar trabajo de `agente-backend` y
`agente-frontend`. No se reescriben entradas anteriores.

---

## 2026-09-06 — Post-merge BE-05..BE-08 (casos de uso) + FE-04..FE-09 (rediseño + casos de prueba)

**Contexto:** recién fusionados en `master` los commits de BE-05..BE-08
(pipeline parametrizado por caso de uso + 3 casos nuevos: calculadora,
leads de zapatillas, encuesta) y FE-04..FE-09 (paleta clara "inteligenze",
logo, tabs en Backlog, sección "Casos de prueba" en el Panel + 3 páginas de
demo). `git log` en el momento de arrancar:
`d91c039 merge: FE-06..FE-09`, `470b67d merge: FE-04, FE-05, BE-05..BE-08`.

### Verificación estática

Backend (`backend/.venv`):
- `ruff check .` → **OK**, "All checks passed!".
- `ruff format --check .` → **OK**, "55 files already formatted".
- `mypy app/dominio` → **OK**, "Success: no issues found in 5 source files".
- `pytest -q` → **OK**, **60 passed**, 23 warnings (ver "Hallazgos" abajo:
  todas las warnings son `SAWarning` de SQLAlchemy por reimportación de
  módulos generados en los tests de `test_caso_calculadora.py`,
  `test_caso_encuesta.py`, `test_caso_leads.py` y `test_montaje_generado.py`
  — no rompen la suite, están cubiertas por `extend_existing=True`).

Frontend (`frontend/`):
- `npx tsc --noEmit` → **OK**, sin salida.
- `npm run build` → **OK**, compila y genera 8 rutas estáticas: `/`,
  `/_not-found`, `/backlog`, `/casos/calculadora`, `/casos/encuesta`,
  `/casos/leads_zapatillas`, `/configuracion`, `/items`.

### `./scripts/smoke.sh`

Levanté backend (`uvicorn`, puerto 8000) y frontend (`next dev`, puerto 3000)
en `master` (puertos confirmados libres antes de arrancar). Corrí
`API=http://127.0.0.1:8000 bash scripts/smoke.sh`:

- `GET /api/health` → `200`, `{"ok":true,"brain":"scripted","deploy_enabled":false,...}`.
- `POST /api/run` (sin `caso_de_uso`, comportamiento histórico de Items) →
  `202 Accepted`.
- `GET /api/run/status` tras la corrida → `status:"done"`, los tres agentes
  (`backend`, `frontend`, `deploy`) en `done`, `caso_de_uso:null`.
- `POST /api/items` + `GET /api/items` → `201` y el item creado aparece en
  el listado.

**smoke.sh pasa completo, sin fallos.**

### Verificación manual E2E de los 3 casos de uso nuevos (BE-06/07/08 + FE-07/08/09)

Nota de método: `duracion_paso_demo_s` (config) por defecto es 40s por paso
para que una corrida de un caso nuevo "se sienta como una demo real" (según
el comentario en `config.py`), lo que implica varios minutos por caso. Para
poder verificar los tres casos en la misma sesión arranqué el backend con
`DURACION_PASO_DEMO_S=1` (variable de entorno, sin tocar código) — esto solo
acelera las pausas de logging entre pasos, no cambia qué hace cada agente ni
qué código genera.

**GET /api/casos-de-uso** → `200`, devuelve los 4 casos (`items`,
`calculadora`, `leads_zapatillas`, `encuesta`) con `id/nombre/descripcion/icono`.

**Calculadora** (`POST /api/run {"caso_de_uso":"calculadora"}`):
- Corrida terminó en `status:"done"`, `caso_de_uso:"calculadora"`.
- Se montó `app/generated/calculadora_routes.py` (log: "Router generado
  montado desde ...calculadora_routes.py").
- `POST /api/calculadora/registro` → `201`; repetido con el mismo usuario →
  `409` (correcto).
- `POST /api/calculadora/login` con clave correcta → `200` + token; con
  clave incorrecta → `401`.
- `POST /api/calculadora/operar` autenticado (10 + 5) → `200`,
  `resultado:15`; división por cero → `400` "No se puede dividir por cero";
  sin token → `401`.
- `GET /api/calculadora/historial` autenticado → `200`, devuelve la
  operación hecha.
- **Persistencia real verificada con `sqlite3` directo sobre
  `backend/orquesta.db`**: tablas `calculadora_usuarios`,
  `calculadora_sesiones`, `calculadora_operaciones` existen y contienen las
  filas esperadas (usuario `ana` con hash/salt propios, la operación
  `10 + 5 = 15`).
- Página `/casos/calculadora` → `200`; leí `Calculadora.tsx` generado y
  coincide exactamente con los campos y rutas del router generado
  (`token`, `Operacion{id,a,b,operador,resultado,creado_en}`,
  `Authorization: Bearer`).

**Leads de zapatillas** (`caso_de_uso:"leads_zapatillas"`):
- Corrida `done`. Se montó `leads_routes.py`.
- `POST /api/leads` con datos válidos → `201` con el lead creado.
- `POST /api/leads` con `nombre` vacío → `422` (validación Pydantic
  `min_length=1`).
- `GET /api/leads` → `200`, lista el lead recién creado, más reciente
  primero.
- Página `/casos/leads_zapatillas` → `200`; `FormularioLeads.tsx` generado
  coincide con el contrato del router (mismos campos, mismo POST/GET).

**Encuesta de satisfacción** (`caso_de_uso:"encuesta"`):
- Corrida `done`. Se montó `encuesta_routes.py`.
- 5 `POST /api/encuesta` con puntajes `5,4,3,5,1` → `201` cada uno.
- `POST /api/encuesta` con puntaje `6` y con `0` → `422` en ambos casos
  (`ge=1, le=5`).
- `GET /api/encuesta/resultados` → `200`,
  `{"total":5,"promedio":3.6,"conteo_por_puntaje":{"1":1,"2":0,"3":1,"4":1,"5":2}}`
  — aritmética correcta (suma 18/5 = 3.6).
- Página `/casos/encuesta` → `200`; `Encuesta.tsx` generado consume
  exactamente `resultados.total/promedio/conteo_por_puntaje` como los
  devuelve el router.

**Conclusión: los 3 casos nuevos funcionan de punta a punta** — se lanzan
desde el pipeline (`POST /api/run` con `caso_de_uso`), su router se monta
dinámicamente, persisten datos reales en SQLite (no en memoria), y sus
páginas de frontend muestran exactamente lo que el backend generado expone.
También verifiqué `GET /api/backlog` (17 tareas, cada una con `lado`
correcto BE/FE) y que las páginas `/`, `/backlog`, `/configuracion`,
`/items` responden `200` con el tema nuevo, y que
`frontend/public/logo-inteligenze.webp` existe y se sirve (`200`).

Serví ambos procesos (`uvicorn`, `next dev`) y los corté al terminar;
borré los archivos que generó mi propia sesión de prueba
(`app/generated/{calculadora,leads,encuesta}_routes.py`, `orquesta.db`)
para no ensuciar el working tree — no son cambios de código, son
artefactos de datos/generados en tiempo de ejecución.

### Hallazgos (no corregidos — quedan para el backlog)

1. **`.gitignore` incompleto para código generado.** Solo ignora
   `backend/app/generated/item_routes.py` (línea 9). Los tres archivos
   nuevos que puede escribir el `BackendAgent`
   (`calculadora_routes.py`, `leads_routes.py`, `encuesta_routes.py`)
   no están listados, así que después de correr cualquiera de los 3 casos
   nuevos aparecen como `??` (sin trackear) en `git status` — lo comprobé
   corriendo los 3 casos y viendo los 3 archivos en `git status --short`.
   `backend/app/generated/` solo debería trackear `.gitkeep` e
   `__init__.py`, igual que hoy con `item_routes.py`.

2. **`montar_router_generado` remonta TODO en cada corrida, no solo el caso
   recién generado.** `main.py:_post_corrida` llama
   `montar_router_generado(app)` al terminar cualquier corrida, y esa
   función itera **todos** los archivos de `archivos_backend_generados()`
   que existan en disco y hace `app.include_router(...)` de nuevo sobre
   cada uno — incluidos los que ya estaban montados de corridas anteriores.
   Lo confirmé en los logs del `uvicorn` real: después de la corrida de
   Items se volvió a montar `item_routes.py`; después de la de calculadora
   se remontaron `item_routes.py` **y** `calculadora_routes.py`; después de
   la de leads se remontaron los tres anteriores más `leads_routes.py`, y
   así sucesivamente. Cada remontaje también reimporta el módulo Python
   generado bajo un nuevo `spec`, lo que dispara
   `SAWarning: This declarative base already contains a class with the same
   class name...` de SQLAlchemy por cada clase ORM del caso (visto también
   en la suite de pytest, 23 warnings). `test_montaje_generado.py` ya
   documenta que esto "no debe explotar" y no explota (gracias a
   `extend_existing=True`), pero no hay deduplicación: `app.routes` va
   acumulando objetos `Route` repetidos para el mismo path en cada corrida,
   dentro del mismo proceso de larga duración. No es un fallo funcional
   (los endpoints responden bien, lo verifiqué extensamente arriba) pero sí
   una acumulación silenciosa que vale la pena resolver antes de que el
   proceso quede corriendo días en producción.

3. **`duracion_paso_demo_s=40.0` por defecto** hace que una corrida real de
   cualquiera de los 3 casos nuevos tarde varios minutos (backend + frontend
   agent, con 2-3 pausas de 40s cada uno) — es intencional según el
   comentario en `config.py` ("se sienta como una demo real, ~4-6
   minutos"), no un bug, pero documento acá que la verificación manual
   E2E de esta sesión se hizo con `DURACION_PASO_DEMO_S=1` (variable de
   entorno) para no bloquear la sesión de revisión con minutos de espera
   por caso — no cambia el código ni qué genera cada agente.

4. **Desvío menor respecto a la especificación de FE-06:** el backlog pedía
   que el botón "Ejecutar agentes" genérico (Items) quedara "más chico,
   como cuarta opción". En la implementación actual, `CasoDePruebaCard`
   renderiza las 4 opciones (`items`, `calculadora`, `leads_zapatillas`,
   `encuesta`) con el mismo tamaño y markup — no hay una variante visual
   más chica para Items. Funcionalmente Items sigue siendo la cuarta
   tarjeta de la grilla y funciona igual que las demás; es una diferencia
   cosmética frente al criterio de diseño pedido, no un error.

---
