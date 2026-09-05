"""Credenciales de Vercel/Render: persistencia, preferencia de token en el
desplegador, y traducción de errores de las APIs externas. Los httpx.AsyncClient
se simulan — estas pruebas no llaman a Vercel ni a Render de verdad.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adaptadores import fabricas, oauth_vercel, render_api
from app.adaptadores.persistencia_sqlalchemy import (
    Base,
    RepositorioCredencialRenderSQLAlchemy,
    RepositorioCredencialVercelSQLAlchemy,
)
from app.config import config
from app.dominio.errores import CredencialInvalida, OAuthFallido
from app.dominio.modelos import CredencialRender, CredencialVercel


@pytest.fixture
async def sesion() -> AsyncIterator[object]:
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        yield s
    await motor.dispose()


class _RespuestaFalsa:
    def __init__(self, status_code: int, cuerpo: object) -> None:
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self) -> object:
        return self._cuerpo

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            peticion = httpx.Request("GET", "https://ejemplo.invalido")
            raise httpx.HTTPStatusError("error", request=peticion, response=self)  # type: ignore[arg-type]


class _ClienteFalso:
    def __init__(self, respuesta: _RespuestaFalsa) -> None:
        self._respuesta = respuesta

    async def __aenter__(self) -> _ClienteFalso:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, *args: object, **kwargs: object) -> _RespuestaFalsa:
        return self._respuesta

    async def get(self, *args: object, **kwargs: object) -> _RespuestaFalsa:
        return self._respuesta


# --- persistencia ---


async def test_credencial_vercel_guardar_y_obtener(sesion: object) -> None:
    repo = RepositorioCredencialVercelSQLAlchemy(sesion)
    assert await repo.obtener() is None

    await repo.guardar(CredencialVercel(access_token="tok_1", team_id="team_x"))
    obtenida = await repo.obtener()
    assert obtenida is not None
    assert obtenida.access_token == "tok_1"
    assert obtenida.team_id == "team_x"

    # Guardar de nuevo reemplaza la fila (id=1), no duplica.
    await repo.guardar(CredencialVercel(access_token="tok_2", team_id=None))
    obtenida = await repo.obtener()
    assert obtenida.access_token == "tok_2"
    assert obtenida.team_id is None

    await repo.eliminar()
    assert await repo.obtener() is None


async def test_credencial_render_guardar_y_obtener(sesion: object) -> None:
    repo = RepositorioCredencialRenderSQLAlchemy(sesion)
    assert await repo.obtener() is None

    await repo.guardar(CredencialRender(api_key="rnd_123"))
    obtenida = await repo.obtener()
    assert obtenida is not None
    assert obtenida.api_key == "rnd_123"

    await repo.eliminar()
    assert await repo.obtener() is None


# --- construir_desplegador: preferencia de token ---


class _CredencialesFalsas:
    def __init__(self, credencial: CredencialVercel | None) -> None:
        self._credencial = credencial

    async def guardar(self, credencial: CredencialVercel) -> None:
        self._credencial = credencial

    async def obtener(self) -> CredencialVercel | None:
        return self._credencial

    async def eliminar(self) -> None:
        self._credencial = None


async def test_construir_desplegador_prefiere_token_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "deploy_enabled", True)
    monkeypatch.setattr(config, "vercel_token", "token-del-env")

    credenciales = _CredencialesFalsas(CredencialVercel(access_token="token-oauth"))
    desplegador = await fabricas.construir_desplegador(credenciales)

    assert desplegador._token == "token-oauth"  # type: ignore[attr-defined]


async def test_construir_desplegador_cae_al_token_del_env_sin_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "deploy_enabled", True)
    monkeypatch.setattr(config, "vercel_token", "token-del-env")

    desplegador = await fabricas.construir_desplegador(_CredencialesFalsas(None))

    assert desplegador._token == "token-del-env"  # type: ignore[attr-defined]


async def test_construir_desplegador_simulado_si_deploy_apagado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "deploy_enabled", False)

    desplegador = await fabricas.construir_desplegador(_CredencialesFalsas(None))

    assert type(desplegador).__name__ == "DespliegueSimulado"


# --- intercambio OAuth con Vercel ---


async def test_intercambiar_code_sin_credenciales_configuradas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "vercel_client_id", None)
    with pytest.raises(OAuthFallido, match="VERCEL_CLIENT_ID"):
        await oauth_vercel.intercambiar_code("code-x")


async def test_intercambiar_code_exitoso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "vercel_client_id", "id")
    monkeypatch.setattr(config, "vercel_client_secret", "secreto")

    respuesta = _RespuestaFalsa(200, {"access_token": "tok_abc", "team_id": "team_1"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    credencial = await oauth_vercel.intercambiar_code("code-x")
    assert credencial.access_token == "tok_abc"
    assert credencial.team_id == "team_1"


async def test_intercambiar_code_con_error_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "vercel_client_id", "id")
    monkeypatch.setattr(config, "vercel_client_secret", "secreto")

    respuesta = _RespuestaFalsa(400, {"error": "invalid_grant"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    with pytest.raises(OAuthFallido):
        await oauth_vercel.intercambiar_code("code-x")


# --- API de Render ---


async def test_obtener_usuario_key_invalida(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = _RespuestaFalsa(401, {})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    with pytest.raises(CredencialInvalida):
        await render_api.obtener_usuario("key-mala")


async def test_obtener_usuario_exitoso(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = _RespuestaFalsa(200, {"email": "vos@ejemplo.com", "name": "Vos"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    usuario = await render_api.obtener_usuario("key-buena")
    assert usuario["email"] == "vos@ejemplo.com"


async def test_buscar_servicio_sin_resultados(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = _RespuestaFalsa(200, [])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    assert await render_api.buscar_servicio("key-buena", "orquesta-backend") is None
