"""Adaptador del puerto RepositorioBacklog: lee y agrega tareas a docs/BACKLOG.md.

docs/BACKLOG.md sigue siendo la única fuente de verdad — la misma que leen
`/tarea` y `revisor` (ver CLAUDE.md). Este adaptador no inventa un
almacenamiento paralelo; parsea y agrega secciones al mismo archivo.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..dominio.modelos import Lado, TareaBacklog

_PATRON_ENCABEZADO = re.compile(r"^([A-Za-z]{2}-\d+)\s+—\s+(.+)$")


class RepositorioBacklogMarkdown:
    def __init__(self, ruta: Path) -> None:
        self._ruta = ruta

    def listar(self) -> list[TareaBacklog]:
        if not self._ruta.is_file():
            return []

        contenido = self._ruta.read_text(encoding="utf-8")
        # El preámbulo (antes de la primera "## ") no es una tarea; se descarta.
        secciones = re.split(r"(?m)^## ", contenido)[1:]

        tareas: list[TareaBacklog] = []
        for seccion in secciones:
            lineas = seccion.splitlines()
            if not lineas:
                continue
            coincidencia = _PATRON_ENCABEZADO.match(lineas[0].strip())
            if not coincidencia:
                continue

            id_tarea, titulo = coincidencia.group(1), coincidencia.group(2)
            cuerpo = "\n".join(lineas[1:]).strip()
            cuerpo = re.sub(r"\n?-{3,}\s*$", "", cuerpo).strip()
            prefijo = id_tarea[:2].upper()
            lado: Lado = prefijo if prefijo in ("BE", "FE", "DE") else "FE"  # type: ignore[assignment]
            tareas.append(TareaBacklog(id=id_tarea, titulo=titulo, cuerpo=cuerpo, lado=lado))

        return tareas

    def agregar(self, tarea: TareaBacklog) -> None:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        seccion = f"\n## {tarea.id} — {tarea.titulo}\n\n{tarea.cuerpo}\n\n---\n"
        with self._ruta.open("a", encoding="utf-8") as archivo:
            archivo.write(seccion)
