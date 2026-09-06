"""main.py:montar_router_generado — monta varios casos de uso a la vez (BE-05)
y sobrevive a un remontaje en el mismo proceso, como pasa después de cada
corrida nueva.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import main as app_main
from app.adaptadores import persistencia_sqlalchemy
from app.agents.plantillas import ROUTER_ITEMS
from app.agents.plantillas_calculadora import ROUTER_CALCULADORA
from app.config import config


@pytest.fixture
async def _sqlite_en_memoria(monkeypatch: pytest.MonkeyPatch) -> None:
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    monkeypatch.setattr(persistencia_sqlalchemy, "motor", motor)
    monkeypatch.setattr(persistencia_sqlalchemy, "FabricaSesion", fabrica)


async def test_monta_varios_casos_y_sobrevive_a_un_remontaje(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _sqlite_en_memoria: None
) -> None:
    monkeypatch.setattr(config, "dir_generado_backend", str(tmp_path))
    (tmp_path / "item_routes.py").write_text(ROUTER_ITEMS, encoding="utf-8")
    (tmp_path / "calculadora_routes.py").write_text(ROUTER_CALCULADORA, encoding="utf-8")

    app = FastAPI()
    assert app_main.montar_router_generado(app) is True
    await persistencia_sqlalchemy.crear_tablas()

    rutas = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/api/items" in rutas
    assert "/api/calculadora/registro" in rutas

    # Simula lo que pasa después de una corrida siguiente: se vuelve a montar
    # sin reiniciar el proceso. No debe explotar por tablas/índices duplicados.
    assert app_main.montar_router_generado(app) is True


async def test_no_monta_nada_si_no_hay_archivos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "dir_generado_backend", str(tmp_path))
    app = FastAPI()
    assert app_main.montar_router_generado(app) is False
