"""Credenciales de Vercel/Render: persistencia, preferencia de token en el
desplegador, y traducción de errores de las APIs externas. Los httpx.AsyncClient
se simulan — estas pruebas no llaman a Vercel ni a Render de verdad.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adaptadores import fabricas, oauth_vercel, render_api
from app.adaptadores.persistencia_sqlalchemy import (
    Base,
    RepositorioCredencialRenderSQLAlchemy,
    RepositorioCredencialVercelSQLAlchemy,
    RepositorioUsoAnthropicSQLAlchemy,
)
from app.config import config
from app.dominio.errores import CredencialInvalida, OAuthFallido
from app.dominio.modelos import CredencialRender, CredencialVercel, UsoAnthropic


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


async def test_uso_anthropic_establecer_limite_y_sumar_tokens(sesion: object) -> None:
    repo = RepositorioUsoAnthropicSQLAlchemy(sesion)
    assert await repo.obtener() is None

    registro = await repo.establecer_limite(1000)
    assert registro.limite_tokens == 1000
    assert registro.tokens_usados == 0

    registro = await repo.sumar_tokens(120)
    registro = await repo.sumar_tokens(80)
    assert registro.tokens_usados == 200

    # Cambiar el límite no reinicia el contador acumulado.
    registro = await repo.establecer_limite(500)
    assert registro.limite_tokens == 500
    assert registro.tokens_usados == 200


async def test_uso_anthropic_sumar_tokens_sin_limite_configurado(sesion: object) -> None:
    repo = RepositorioUsoAnthropicSQLAlchemy(sesion)

    registro = await repo.sumar_tokens(50)
    assert registro.limite_tokens == 0
    assert registro.tokens_usados == 50


def test_porcentaje_uso_anthropic() -> None:
    assert UsoAnthropic(limite_tokens=0, tokens_usados=50).porcentaje() == 0.0
    assert UsoAnthropic(limite_tokens=200, tokens_usados=20).porcentaje() == 10.0
    assert UsoAnthropic(limite_tokens=200, tokens_usados=400).porcentaje() == 100.0


# --- despliegue de la fábrica: simulado salvo que una persona lo active ---


def test_desplegador_de_la_fabrica_es_simulado_si_deploy_apagado(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "deploy_enabled", False)
    desplegador = fabricas.construir_desplegador_fabrica(tmp_path, "abc123", "Fábrica: prueba")
    assert type(desplegador).__name__ == "DespliegueGitHubSimulado"


def test_desplegador_de_la_fabrica_es_github_si_deploy_encendido(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "deploy_enabled", True)
    desplegador = fabricas.construir_desplegador_fabrica(tmp_path, "abc123", "Fábrica: prueba")
    assert type(desplegador).__name__ == "DespliegueGitHub"


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
