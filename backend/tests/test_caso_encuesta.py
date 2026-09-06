"""Caso de uso "encuesta": respuestas 1-5 y resultados agregados, contra
SQLite en memoria.
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adaptadores import persistencia_sqlalchemy
from app.agents.plantillas_encuesta import ROUTER_ENCUESTA


@pytest.fixture
async def cliente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    monkeypatch.setattr(persistencia_sqlalchemy, "motor", motor)
    monkeypatch.setattr(persistencia_sqlalchemy, "FabricaSesion", fabrica)

    archivo = tmp_path / "encuesta_routes.py"
    archivo.write_text(ROUTER_ENCUESTA, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("app.generated._test_encuesta", archivo)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    await persistencia_sqlalchemy.crear_tablas()

    app = FastAPI()
    app.include_router(modulo.router)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await motor.dispose()


async def test_resultados_agregados(cliente: httpx.AsyncClient) -> None:
    for puntaje in (5, 5, 3, 1):
        r = await cliente.post("/api/encuesta", json={"puntaje": puntaje})
        assert r.status_code == 201

    r = await cliente.get("/api/encuesta/resultados")
    assert r.status_code == 200
    datos = r.json()
    assert datos["total"] == 4
    assert datos["promedio"] == pytest.approx(3.5)
    assert datos["conteo_por_puntaje"] == {"1": 1, "2": 0, "3": 1, "4": 0, "5": 2}


async def test_resultados_sin_respuestas(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/encuesta/resultados")
    assert r.status_code == 200
    datos = r.json()
    assert datos["total"] == 0
    assert datos["promedio"] == 0.0


async def test_puntaje_fuera_de_rango_da_422(cliente: httpx.AsyncClient) -> None:
    assert (await cliente.post("/api/encuesta", json={"puntaje": 0})).status_code == 422
    assert (await cliente.post("/api/encuesta", json={"puntaje": 6})).status_code == 422


async def test_comentario_opcional(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/encuesta", json={"puntaje": 4, "comentario": "muy bueno"})
    assert r.status_code == 201
    assert r.json()["comentario"] == "muy bueno"
