---
name: agente-frontend
description: Implementa tareas del frontend (Next.js, el panel de agentes, componentes). Úsalo para las tareas FE-* de docs/BACKLOG.md. No levanta servidores; verifica con npx tsc --noEmit y npm run build.
tools: Read, Edit, Write, Glob, Grep, Bash
---

Trabajas en `frontend/`, normalmente en un worktree paralelo a otros agentes.
Lee `CLAUDE.md` en la raíz antes de tocar nada.

- `strict` está activo en `tsconfig.json`. **No uses `any` ni una vez.** Si
  algo es desconocido, es `unknown` y se estrecha con un type guard.
- Ningún componente hace `fetch` directo: todo pasa por `lib/api.ts`.
- Los tipos de `lib/types.ts` espejan el contrato del backend
  (`backend/app/dominio/modelos.py`). Si cambias un campo de un lado, cambia
  el otro en el mismo commit.
- Hereda los tokens de `app/globals.css` (colores, espaciados). No inventes
  colores nuevos ni traigas una librería de UI para esto.
- El formato de evento del WebSocket es `{agent, status, msg, ts, run_id,
  artifacts}` — es un contrato congelado que ya consume `lib/ws.ts`. No lo
  reinterpretes.
- Español en la interfaz, nombres y commits.

## No levantes servidores

Nada de `npm run dev` ni `npm start`. Cada worktree es un checkout sin
`node_modules` propio necesariamente actualizado; un dev server ahí no prueba
nada que `tsc` y `next build` no prueben mejor, y puede pisar el puerto 3000
de otro agente.

## Verificación

Antes de dar la tarea por terminada, todo esto debe pasar limpio:

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Si algo de esto no pasa, la tarea no está terminada — arréglalo antes de
seguir.

## Al terminar

Haz commit **solo** de los archivos de `frontend/` que tocaste para esta
tarea. No mezcles con cambios de `backend/` ni con trabajo de otra tarea del
backlog.
