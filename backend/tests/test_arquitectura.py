"""Verifica que backend/app/dominio no dependa de infraestructura.

Una regla de arquitectura que no se verifica se erosiona en dos semanas.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROHIBIDOS = {"fastapi", "sqlalchemy", "httpx", "os"}
RAIZ_DOMINIO = Path(__file__).resolve().parent.parent / "app" / "dominio"


def _arbol(archivo: Path) -> ast.Module:
    return ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))


def test_dominio_no_importa_infraestructura() -> None:
    archivos = list(RAIZ_DOMINIO.rglob("*.py"))
    assert archivos, "No se encontraron archivos en app/dominio"

    violaciones: list[str] = []
    for archivo in archivos:
        for nodo in ast.walk(_arbol(archivo)):
            if isinstance(nodo, ast.Import):
                modulos = {alias.name.split(".")[0] for alias in nodo.names}
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                modulos = {nodo.module.split(".")[0]}
            else:
                continue
            for modulo in modulos & PROHIBIDOS:
                violaciones.append(f"{archivo.relative_to(RAIZ_DOMINIO)} importa '{modulo}'")

    assert not violaciones, "\n".join(violaciones)


def test_dominio_no_importa_config() -> None:
    archivos = list(RAIZ_DOMINIO.rglob("*.py"))

    violaciones: list[str] = []
    for archivo in archivos:
        for nodo in ast.walk(_arbol(archivo)):
            if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.endswith("config"):
                violaciones.append(f"{archivo.relative_to(RAIZ_DOMINIO)} importa '{nodo.module}'")

    assert not violaciones, "\n".join(violaciones)
