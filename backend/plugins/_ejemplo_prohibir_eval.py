"""Plugin de ejemplo: una compuerta tipo SAST mínima.

Veta la aprobación de una especificación si su código Python llama a
`eval` o `exec`. Está desactivado (el nombre empieza con "_"); para usarlo,
renombralo a `prohibir_eval.py` y reiniciá el backend.

Ver app/orchestrator/plugins.py para la lista de eventos y compuertas.
"""

import ast
from pathlib import Path

PROHIBIDAS = {"eval", "exec"}


def vetar_eval(encargo_id: str, espec_id: str, espacio: Path, archivos: list[str]) -> str | None:
    for ruta in archivos:
        if not ruta.endswith(".py"):
            continue
        arbol = ast.parse((espacio / ruta).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id in PROHIBIDAS
            ):
                return f"{ruta}:{nodo.lineno} usa {nodo.func.id}(), prohibido por la política"
    return None


def registrar(plugins) -> None:  # type: ignore[no-untyped-def]
    plugins.compuerta("antes_de_aprobar", vetar_eval)
