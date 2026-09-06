"""Caso de uso "leads_zapatillas": alta pública y listado, contra SQLite en
memoria.
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
from app.agents.plantillas_leads import ROUTER_LEADS


@pytest.fixture
async def cliente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    monkeypatch.setattr(persistencia_sqlalchemy, "motor", motor)
    monkeypatch.setattr(persistencia_sqlalchemy, "FabricaSesion", fabrica)

    archivo = tmp_path / "leads_routes.py"
    archivo.write_text(ROUTER_LEADS, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("app.generated._test_leads", archivo)
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


async def test_crear_y_listar_mas_recientes_primero(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post(
        "/api/leads",
        json={
            "nombre": "Ana",
            "email": "ana@example.com",
            "telefono": "123",
            "talla": "38",
            "comentario": "quiero las nuevas",
        },
    )
    assert r.status_code == 201
    primero = r.json()

    r = await cliente.post("/api/leads", json={"nombre": "Beto", "email": "beto@example.com"})
    assert r.status_code == 201
    segundo = r.json()

    r = await cliente.get("/api/leads")
    assert r.status_code == 200
    leads = r.json()
    assert [lead["id"] for lead in leads] == [segundo["id"], primero["id"]]


async def test_nombre_vacio_da_422(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/leads", json={"nombre": "", "email": "a@b.com"})
    assert r.status_code == 422


async def test_email_sin_arroba_da_422(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/leads", json={"nombre": "Ana", "email": "no-es-un-email"})
    assert r.status_code == 422
