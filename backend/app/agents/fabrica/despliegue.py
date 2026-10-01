"""Despliegue del encargo: deja el workflow de CI/CD en el espacio de trabajo
y le pasa el control al Desplegador (GitHub, real o simulado).

El workflow lo escribe el harness, no un LLM: es la misma receta para todos
los encargos, y es lo que GitHub Actions va a correr sobre el PR.
"""

from __future__ import annotations

from pathlib import Path

from ...dominio.puertos import Desplegador, EmisorLinea

WORKFLOW_CI = """name: CI de la fábrica

on:
  pull_request:
  push:
    branches: [main]

jobs:
  pruebas:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pytest
      - run: python -m pytest -q
"""


class DespliegueFabrica:
    name = "despliegue"

    async def desplegar(
        self, espacio: Path, desplegador: Desplegador, on_linea: EmisorLinea
    ) -> str | None:
        workflow = espacio / ".github" / "workflows" / "ci.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(WORKFLOW_CI, encoding="utf-8")
        await on_linea("Workflow de GitHub Actions escrito en .github/workflows/ci.yml")
        return await desplegador.ejecutar(on_linea)
