---
description: Delega en el agente revisor para correr el humo y las pruebas completas sobre la rama principal y actualizar docs/BITACORA.md.
---

Confirmá en qué rama estás (`git branch --show-current`). El revisor asume que
corre sobre la rama principal, después de que ya se fusionó trabajo de
`agente-backend` o `agente-frontend` — si estás en un worktree o una rama de
feature, avisá antes de seguir en vez de correrlo igual.

Delegá en el agente `revisor` para que:

1. Corra la verificación completa (lint, tipos, pruebas, `./scripts/smoke.sh`).
2. Documente el resultado en `docs/BITACORA.md`.
3. Proponga qué tareas de `docs/BACKLOG.md` quedaron desbloqueadas o cuáles
   nuevas hacen falta.

El revisor tiene prohibido arreglar código — si encuentra algo roto, lo
diagnostica y lo registra, no lo parcha. Si ves que el resultado incluye un
cambio de código de la aplicación, señalalo: no debería haber pasado.
