"""Un cerebro que devuelve código inválido no debe tumbar al agente ni escribir basura."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.backend_agent import BackendAgent
from app.agents.base import ContextoCorrida
from app.agents.frontend_agent import FrontendAgent
from app.agents.plantillas import LISTA_ITEMS_TSX, ROUTER_ITEMS
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
