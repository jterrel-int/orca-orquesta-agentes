"""RepositorioBacklogMarkdown y ServicioBacklog contra un docs/BACKLOG.md real."""

from __future__ import annotations

from pathlib import Path

from app.adaptadores.backlog_markdown import RepositorioBacklogMarkdown
from app.dominio.servicios import ServicioBacklog

MARKDOWN_DE_PRUEBA = """# Backlog

Intro que no es una tarea.

---

## BE-01 — TestAgent: cuarta etapa del pipeline

Un agente nuevo que corre pytest.

**Archivos:** backend/app/agents/test_agent.py

**Depende de:** nada.

---

## FE-01 — Filtro de logs por agente

Un selector sobre LogStream.

**Depende de:** nada.

---
"""


def test_listar_parsea_las_tareas_existentes(tmp_path: Path) -> None:
    ruta = tmp_path / "BACKLOG.md"
    ruta.write_text(MARKDOWN_DE_PRUEBA, encoding="utf-8")

    tareas = RepositorioBacklogMarkdown(ruta).listar()

    assert [t.id for t in tareas] == ["BE-01", "FE-01"]
    assert tareas[0].titulo == "TestAgent: cuarta etapa del pipeline"
    assert tareas[0].lado == "BE"
    assert "pytest" in tareas[0].cuerpo
    assert tareas[1].lado == "FE"


def test_listar_sobre_archivo_inexistente_devuelve_vacio(tmp_path: Path) -> None:
    assert RepositorioBacklogMarkdown(tmp_path / "no-existe.md").listar() == []


def test_agregar_escribe_una_seccion_nueva(tmp_path: Path) -> None:
    ruta = tmp_path / "BACKLOG.md"
    ruta.write_text(MARKDOWN_DE_PRUEBA, encoding="utf-8")
    repo = RepositorioBacklogMarkdown(ruta)

    servicio = ServicioBacklog(repo)
    creada = servicio.agregar("Nueva tarea", "Descripción de la tarea nueva.", "BE")

    assert creada.id == "BE-02"  # siguiente número disponible para BE

    tareas = repo.listar()
    assert [t.id for t in tareas] == ["BE-01", "FE-01", "BE-02"]
    assert tareas[-1].titulo == "Nueva tarea"
    assert tareas[-1].cuerpo == "Descripción de la tarea nueva."


def test_agregar_sobre_archivo_inexistente_lo_crea(tmp_path: Path) -> None:
    ruta = tmp_path / "subdir" / "BACKLOG.md"
    servicio = ServicioBacklog(RepositorioBacklogMarkdown(ruta))

    creada = servicio.agregar("Primera tarea", "Cuerpo.", "FE")

    assert creada.id == "FE-01"
    assert ruta.is_file()
