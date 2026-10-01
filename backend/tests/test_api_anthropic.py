"""POST/GET/DELETE /api/anthropic/conexion: pegar una API key la verifica
contra la API real antes de guardarla, y el estado nunca devuelve la key
completa.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import anthropic as api_anthropic
from app.dominio.errores import CredencialInvalida


@pytest.fixture
async def cliente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    import app.adaptadores.persistencia_sqlalchemy as persistencia

    motor = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(persistencia, "motor", motor)
    monkeypatch.setattr(
        persistencia,
        "FabricaSesion",
        async_sessionmaker(motor, class_=persistencia.AsyncSession, expire_on_commit=False),
    )
    async with motor.begin() as conexion:
        await conexion.run_sync(persistencia.Base.metadata.create_all)

    app = FastAPI()
    app.include_router(api_anthropic.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_estado_sin_conexion(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/anthropic/estado")
    assert r.status_code == 200
    assert r.json()["conectado"] is False


async def test_conectar_con_key_invalida_da_400(
    cliente: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _falla(api_key: str, modelo: str) -> None:
        raise CredencialInvalida("La API key de Anthropic no es válida")

    monkeypatch.setattr(api_anthropic, "verificar_api_key", _falla)

    r = await cliente.post("/api/anthropic/conexion", json={"api_key": "sk-ant-mala"})

    assert r.status_code == 400


async def test_conectar_con_key_valida_la_guarda_y_la_enmascara(
    cliente: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _ok(api_key: str, modelo: str) -> None:
        return None

    monkeypatch.setattr(api_anthropic, "verificar_api_key", _ok)

    r = await cliente.post("/api/anthropic/conexion", json={"api_key": "sk-ant-0123456789abcd"})

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["conectado"] is True
    assert cuerpo["clave"] == "···abcd"
    assert "0123456789" not in cuerpo["clave"]

    estado = (await cliente.get("/api/anthropic/estado")).json()
    assert estado["conectado"] is True
    assert estado["clave"] == "···abcd"


async def test_desconectar_borra_la_credencial(
    cliente: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _ok(api_key: str, modelo: str) -> None:
        return None

    monkeypatch.setattr(api_anthropic, "verificar_api_key", _ok)
    await cliente.post("/api/anthropic/conexion", json={"api_key": "sk-ant-xyz"})

    r = await cliente.delete("/api/anthropic/conexion")
    assert r.status_code == 204

    estado = (await cliente.get("/api/anthropic/estado")).json()
    assert estado["conectado"] is False


# --- uso: contador local de tokens contra un límite que define el usuario ---


async def test_uso_es_null_sin_limite_configurado(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/anthropic/uso")
    assert r.status_code == 200
    assert r.json() is None

    estado = (await cliente.get("/api/anthropic/estado")).json()
    assert estado["uso"] is None


async def test_establecer_limite_de_uso(cliente: httpx.AsyncClient) -> None:
    r = await cliente.put("/api/anthropic/uso", json={"limite_tokens": 1000})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo == {"limite_tokens": 1000, "tokens_usados": 0, "porcentaje": 0.0}

    r = await cliente.get("/api/anthropic/uso")
    assert r.json() == cuerpo


async def test_establecer_limite_invalido_da_422(cliente: httpx.AsyncClient) -> None:
    r = await cliente.put("/api/anthropic/uso", json={"limite_tokens": 0})
    assert r.status_code == 422


async def test_conexion_y_estado_incluyen_el_uso_configurado(
    cliente: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _ok(api_key: str, modelo: str) -> None:
        return None

    monkeypatch.setattr(api_anthropic, "verificar_api_key", _ok)
    await cliente.put("/api/anthropic/uso", json={"limite_tokens": 200})

    r = await cliente.post("/api/anthropic/conexion", json={"api_key": "sk-ant-0123456789abcd"})
    assert r.json()["uso"] == {"limite_tokens": 200, "tokens_usados": 0, "porcentaje": 0.0}

    estado = (await cliente.get("/api/anthropic/estado")).json()
    assert estado["uso"] == {"limite_tokens": 200, "tokens_usados": 0, "porcentaje": 0.0}
