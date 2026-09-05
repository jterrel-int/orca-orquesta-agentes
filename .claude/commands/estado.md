---
description: Corre las verificaciones estáticas de ambos lados y reporta qué tareas del backlog se pueden lanzar en paralelo ahora mismo.
---

Corré, sin levantar ningún servidor:

```bash
cd backend && ruff check . && mypy app/dominio && pytest -q
cd ../frontend && npx tsc --noEmit
```

Leé `docs/BACKLOG.md` y reportá, en una lista corta:

1. Qué tareas siguen pendientes, con su ID.
2. De esas, cuáles no tienen una dependencia pendiente (columna "Depende de"
   vacía o ya resuelta).
3. De las lanzables, cuáles se pueden correr en paralelo ahora mismo: dos
   tareas son paralelizables si una es `BE-*` y la otra `FE-*`, o si ambas son
   del mismo lado pero tocan archivos que no se superponen.

Si ruff, mypy, pytest o tsc fallan, decilo primero — no tiene sentido lanzar
tareas nuevas sobre una base que no verifica limpio.
