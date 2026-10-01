"""La app arranca contra una base de datos vacía: la primera vez que alguien
clona el repo, levanta Docker o despliega con disco limpio.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.adaptadores.fabricas as fabricas
import app.adaptadores.persistencia_sqlalchemy as persistencia
from app.main import app, ciclo_vida


async def test_arranca_con_una_base_vacia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    motor = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'vacia.db'}")
    monkeypatch.setattr(persistencia, "motor", motor)
    monkeypatch.setattr(
        persistencia,
        "FabricaSesion",
        async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False),
    )
    # El Líder es un singleton que captura la fábrica de sesiones al crearse.
    monkeypatch.setattr(fabricas, "_lider", None)

    async with ciclo_vida(app), motor.connect() as conexion:
        tablas = await conexion.run_sync(lambda c: set(inspect(c).get_table_names()))

    assert {
        "fabrica_encargos",
        "fabrica_bitacora",
        "fabrica_metricas",
        "fabrica_cache_llm",
        "credenciales_anthropic",
    } <= tablas
    await motor.dispose()
