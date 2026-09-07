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

## DE-01 — Notificar despliegues fallidos

Avisar cuando un deploy falla.

**Depende de:** nada.

---
"""


def test_listar_parsea_las_tareas_existentes(tmp_path: Path) -> None:
    ruta = tmp_path / "BACKLOG.md"
    ruta.write_text(MARKDOWN_DE_PRUEBA, encoding="utf-8")

    tareas = RepositorioBacklogMarkdown(ruta).listar()

    assert [t.id for t in tareas] == ["BE-01", "FE-01", "DE-01"]
    assert tareas[0].titulo == "TestAgent: cuarta etapa del pipeline"
    assert tareas[0].lado == "BE"
    assert "pytest" in tareas[0].cuerpo
    assert tareas[1].lado == "FE"
    assert tareas[2].lado == "DE"


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
    assert [t.id for t in tareas] == ["BE-01", "FE-01", "DE-01", "BE-02"]
    assert tareas[-1].titulo == "Nueva tarea"
    assert tareas[-1].cuerpo == "Descripción de la tarea nueva."


def test_agregar_sobre_archivo_inexistente_lo_crea(tmp_path: Path) -> None:
    ruta = tmp_path / "subdir" / "BACKLOG.md"
    servicio = ServicioBacklog(RepositorioBacklogMarkdown(ruta))

    creada = servicio.agregar("Primera tarea", "Cuerpo.", "FE")

    assert creada.id == "FE-01"
    assert ruta.is_file()


# --- generar_desde_especificacion: sin cerebro real, división heurística ---

ESPECIFICACION_DE_PRUEBA = """# Login de usuarios

Hace falta un endpoint de autenticación con base de datos y modelo de sesión.

# Pantalla de bienvenida

Un componente de React con un formulario y un botón de inicio de sesión.

# Notificaciones por email

Avisar por correo cuando se completa un pedido.
"""


async def test_generar_sin_cerebro_usa_division_heuristica(tmp_path: Path) -> None:
    ruta = tmp_path / "BACKLOG.md"
    servicio = ServicioBacklog(RepositorioBacklogMarkdown(ruta))

    creadas = await servicio.generar_desde_especificacion(ESPECIFICACION_DE_PRUEBA, "BE")

    assert len(creadas) == 3
    assert all(t.lado == "BE" for t in creadas)  # alcance="BE" fuerza el lado en las 3
    assert creadas[0].titulo == "Login de usuarios"
    assert "base de datos" in creadas[0].cuerpo
    assert [t.id for t in creadas] == ["BE-01", "BE-02", "BE-03"]


async def test_generar_con_alcance_todo_reparte_por_palabras_clave(tmp_path: Path) -> None:
    ruta = tmp_path / "BACKLOG.md"
    servicio = ServicioBacklog(RepositorioBacklogMarkdown(ruta))

    creadas = await servicio.generar_desde_especificacion(ESPECIFICACION_DE_PRUEBA, "todo")

    por_titulo = {t.titulo: t.lado for t in creadas}
    assert por_titulo["Login de usuarios"] == "BE"  # "autenticación", "base de datos", "modelo"
    assert por_titulo["Pantalla de bienvenida"] == "FE"  # "componente", "formulario", "botón"


async def test_generar_documento_sin_encabezados_da_una_sola_tarea(tmp_path: Path) -> None:
    servicio = ServicioBacklog(RepositorioBacklogMarkdown(tmp_path / "BACKLOG.md"))

    creadas = await servicio.generar_desde_especificacion(
        "Un párrafo suelto sin ningún encabezado ni lista numerada.", "FE"
    )

    assert len(creadas) == 1
    assert creadas[0].lado == "FE"


class _CerebroFalso:
    """Cerebro de prueba: devuelve JSON fijo, ignora la instrucción."""

    def __init__(self, respuesta: str) -> None:
        self._respuesta = respuesta

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return self._respuesta


async def test_generar_usa_lo_que_devuelve_el_cerebro_si_es_json_valido(tmp_path: Path) -> None:
    cerebro = _CerebroFalso(
        '[{"lado": "BE", "titulo": "Endpoint de login", "cuerpo": "Hacer el endpoint."}]'
    )
    servicio = ServicioBacklog(RepositorioBacklogMarkdown(tmp_path / "BACKLOG.md"), cerebro)

    creadas = await servicio.generar_desde_especificacion(ESPECIFICACION_DE_PRUEBA, "todo")

    assert len(creadas) == 1
    assert creadas[0].titulo == "Endpoint de login"
    assert creadas[0].lado == "BE"


async def test_generar_cae_a_heuristica_si_el_cerebro_devuelve_basura(tmp_path: Path) -> None:
    cerebro = _CerebroFalso("esto no es JSON")
    servicio = ServicioBacklog(RepositorioBacklogMarkdown(tmp_path / "BACKLOG.md"), cerebro)

    creadas = await servicio.generar_desde_especificacion(ESPECIFICACION_DE_PRUEBA, "BE")

    assert len(creadas) == 3  # la misma división heurística que sin cerebro
