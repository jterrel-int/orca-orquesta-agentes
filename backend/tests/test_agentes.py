"""Un cerebro que devuelve código inválido no debe tumbar al agente ni escribir basura."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.agents.backend_agent import BackendAgent
from app.agents.base import ContextoCorrida
from app.agents.frontend_agent import FrontendAgent
from app.agents.plantillas import LISTA_ITEMS_TSX, ROUTER_ITEMS
from app.agents.plantillas_calculadora import CALCULADORA_TSX, ROUTER_CALCULADORA
from app.config import config
from app.dominio.modelos import EventoAgente


class CerebroRoto:
    """Simula un LLM que devuelve basura sintáctica."""

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return "esto no es python válido &&& {{{"


class CerebroSinExportDefault:
    """Simula un LLM que olvida exportar el componente por defecto."""

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return "export function ListaItems() { return null; }"


async def _emitir_a(lista: list[EventoAgente], evento: EventoAgente) -> None:
    lista.append(evento)


async def test_backend_agent_cae_a_la_plantilla_si_el_codigo_no_compila(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "dir_generado_backend", str(tmp_path))
    eventos: list[EventoAgente] = []
    ctx = ContextoCorrida(run_id="t1", emitir=lambda e: _emitir_a(eventos, e))

    agente = BackendAgent(cerebro=CerebroRoto())
    await agente.ejecutar(ctx)

    contenido = (tmp_path / "item_routes.py").read_text(encoding="utf-8")
    assert contenido == ROUTER_ITEMS
    assert any("no compila" in e.msg for e in eventos)


async def test_frontend_agent_cae_a_la_plantilla_si_no_exporta_por_defecto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "dir_generado_frontend", str(tmp_path))
    eventos: list[EventoAgente] = []
    ctx = ContextoCorrida(run_id="t2", emitir=lambda e: _emitir_a(eventos, e))

    agente = FrontendAgent(cerebro=CerebroSinExportDefault())
    await agente.ejecutar(ctx)

    contenido = (tmp_path / "ListaItems.tsx").read_text(encoding="utf-8")
    assert contenido == LISTA_ITEMS_TSX
    assert any("no exporta por defecto" in e.msg for e in eventos)


# --- BE-05: caso_de_uso=None sigue siendo exactamente el comportamiento histórico ---


async def test_backend_agent_sin_caso_de_uso_genera_items_como_siempre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "dir_generado_backend", str(tmp_path))
    eventos: list[EventoAgente] = []
    ctx = ContextoCorrida(run_id="t3", emitir=lambda e: _emitir_a(eventos, e))
    # ctx.datos no trae "caso_de_uso": es justo el estado en el que llega hoy.

    agente = BackendAgent(cerebro=CerebroGuionado())
    await agente.ejecutar(ctx)

    contenido = (tmp_path / "item_routes.py").read_text(encoding="utf-8")
    assert contenido == ROUTER_ITEMS
    assert ctx.datos["endpoints"] == [
        "GET /api/items",
        "POST /api/items",
        "GET /api/items/{id}",
        "PUT /api/items/{id}",
        "DELETE /api/items/{id}",
    ]


async def test_frontend_agent_caso_items_explicito_genera_lo_mismo_que_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "dir_generado_frontend", str(tmp_path))
    eventos: list[EventoAgente] = []
    ctx = ContextoCorrida(run_id="t4", emitir=lambda e: _emitir_a(eventos, e))
    ctx.datos["caso_de_uso"] = "items"

    agente = FrontendAgent(cerebro=CerebroGuionado())
    await agente.ejecutar(ctx)

    contenido = (tmp_path / "ListaItems.tsx").read_text(encoding="utf-8")
    assert contenido == LISTA_ITEMS_TSX


# --- BE-05: un caso de uso nuevo selecciona su propia instrucción/respaldo ---


async def test_backend_agent_caso_calculadora_usa_su_propio_respaldo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "dir_generado_backend", str(tmp_path))
    # Los pasos extra de los casos nuevos usan duracion_paso_demo_s; en
    # producción son ~10-20s por paso, acá los bajamos para no volver lenta la
    # suite (ver el comentario en config.py sobre esta decisión).
    monkeypatch.setattr(config, "duracion_paso_demo_s", 0.0)
    eventos: list[EventoAgente] = []
    ctx = ContextoCorrida(run_id="t5", emitir=lambda e: _emitir_a(eventos, e))
    ctx.datos["caso_de_uso"] = "calculadora"

    agente = BackendAgent(cerebro=CerebroGuionado())
    await agente.ejecutar(ctx)

    contenido = (tmp_path / "calculadora_routes.py").read_text(encoding="utf-8")
    assert contenido == ROUTER_CALCULADORA
    assert not (tmp_path / "item_routes.py").exists()
    assert ctx.datos["endpoints"][0] == "POST /api/calculadora/registro"
    assert any("autenticación" in e.msg for e in eventos)


async def test_frontend_agent_caso_calculadora_usa_su_propio_respaldo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "dir_generado_frontend_casos", str(tmp_path))
    monkeypatch.setattr(config, "duracion_paso_demo_s", 0.0)
    eventos: list[EventoAgente] = []
    ctx = ContextoCorrida(run_id="t6", emitir=lambda e: _emitir_a(eventos, e))
    ctx.datos["caso_de_uso"] = "calculadora"
    ctx.datos["endpoints"] = ["POST /api/calculadora/registro"]

    agente = FrontendAgent(cerebro=CerebroGuionado())
    await agente.ejecutar(ctx)

    contenido = (tmp_path / "calculadora" / "Calculadora.tsx").read_text(encoding="utf-8")
    assert contenido == CALCULADORA_TSX
