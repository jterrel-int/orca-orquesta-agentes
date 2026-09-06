"""Caso de uso "calculadora": registro → login → operar → historial, contra
SQLite en memoria. Carga el router generado (respaldo) exactamente como lo
hace main.py:montar_router_generado, para probar el código que de verdad se
monta en la app.
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
from app.agents.plantillas_calculadora import ROUTER_CALCULADORA


@pytest.fixture
async def cliente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    monkeypatch.setattr(persistencia_sqlalchemy, "motor", motor)
    monkeypatch.setattr(persistencia_sqlalchemy, "FabricaSesion", fabrica)

    archivo = tmp_path / "calculadora_routes.py"
    archivo.write_text(ROUTER_CALCULADORA, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("app.generated._test_calculadora", archivo)
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


async def test_flujo_completo_registro_login_operar_historial(
    cliente: httpx.AsyncClient,
) -> None:
    r = await cliente.post("/api/calculadora/registro", json={"usuario": "ana", "clave": "1234"})
    assert r.status_code == 201

    r = await cliente.post("/api/calculadora/login", json={"usuario": "ana", "clave": "1234"})
    assert r.status_code == 200
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await cliente.post(
        "/api/calculadora/operar", json={"a": 6, "b": 3, "operador": "/"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["resultado"] == 2

    r = await cliente.get("/api/calculadora/historial", headers=headers)
    assert r.status_code == 200
    historial = r.json()
    assert len(historial) == 1
    assert historial[0]["resultado"] == 2


async def test_registro_duplicado_da_409(cliente: httpx.AsyncClient) -> None:
    datos = {"usuario": "bruno", "clave": "clave-1"}
    assert (await cliente.post("/api/calculadora/registro", json=datos)).status_code == 201
    assert (await cliente.post("/api/calculadora/registro", json=datos)).status_code == 409


async def test_login_con_clave_incorrecta_da_401(cliente: httpx.AsyncClient) -> None:
    await cliente.post("/api/calculadora/registro", json={"usuario": "carla", "clave": "correcta"})
    r = await cliente.post(
        "/api/calculadora/login", json={"usuario": "carla", "clave": "incorrecta"}
    )
    assert r.status_code == 401


async def test_operar_sin_token_da_401(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/calculadora/operar", json={"a": 1, "b": 2, "operador": "+"})
    assert r.status_code == 401


async def test_historial_sin_token_da_401(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/calculadora/historial")
    assert r.status_code == 401


async def test_division_por_cero_da_400_y_no_se_guarda(cliente: httpx.AsyncClient) -> None:
    await cliente.post("/api/calculadora/registro", json={"usuario": "dana", "clave": "1234"})
    r = await cliente.post("/api/calculadora/login", json={"usuario": "dana", "clave": "1234"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    r = await cliente.post(
        "/api/calculadora/operar", json={"a": 5, "b": 0, "operador": "/"}, headers=headers
    )
    assert r.status_code == 400

    r = await cliente.get("/api/calculadora/historial", headers=headers)
    assert r.json() == []
