---
description: Busca una tarea por ID en docs/BACKLOG.md y la delega al agente que corresponde según el prefijo (BE- o FE-).
argument-hint: <ID de la tarea, p. ej. BE-01>
---

Busca la tarea `$ARGUMENTS` en `docs/BACKLOG.md`.

- Si no existe con ese ID exacto, decilo y no inventes una tarea ni adivines
  cuál quiso decir el usuario.
- Si el ID empieza con `BE-`, delegá la tarea completa al agente
  `agente-backend`.
- Si empieza con `FE-`, delegá al agente `agente-frontend`.
- Si una tarea depende de otra que no está resuelta (columna "Depende de" en
  el backlog), avisá antes de delegar en vez de lanzarla igual.

Al delegar, pasá el contexto completo de la fila del backlog: descripción,
archivos que toca, y criterio de verificación. No resumas de más — el
subagente no ve esta conversación.

Cuando el subagente termine, confirmá dos cosas antes de darlo por bueno:

1. Que verificó de forma estática (sin levantar servidores) y que la
   verificación pasó.
2. Que el commit incluye solo archivos del lado que le tocaba (backend/ o
   frontend/, no ambos).

Si alguna de las dos falla, no la des por terminada — decile al subagente qué
falta.
