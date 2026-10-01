"""CerebroAnthropic.pensar(): además de llamar a la API y devolver el texto,
reporta los tokens consumidos por `registrar_uso` — el mecanismo con el que
Orquesta lleva su propio contador de uso (ver dominio.modelos.UsoAnthropic),
ya que Anthropic no expone el gasto de la cuenta a una API key normal.
"""

from __future__ import annotations

import httpx
import pytest

from app.adaptadores.cerebro_anthropic import CerebroAnthropic


class _RespuestaFalsa:
    def __init__(self, status_code: int, cuerpo: object) -> None:
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self) -> object:
        return self._cuerpo

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            peticion = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
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


async def test_pensar_reporta_los_tokens_consumidos(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = _RespuestaFalsa(
        200,
        {
            "content": [{"type": "text", "text": "hola"}],
            "usage": {"input_tokens": 30, "output_tokens": 12},
        },
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    reportados: list[int] = []

    async def _registrar(tokens: int) -> None:
        reportados.append(tokens)

    cerebro = CerebroAnthropic("sk-ant-test", "claude-x", registrar_uso=_registrar)
    texto = await cerebro.pensar("instrucción", respaldo="respaldo")

    assert texto == "hola"
    assert reportados == [42]


async def test_pensar_sin_registrar_uso_no_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = _RespuestaFalsa(
        200,
        {
            "content": [{"type": "text", "text": "hola"}],
            "usage": {"input_tokens": 5, "output_tokens": 1},
        },
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    cerebro = CerebroAnthropic("sk-ant-test", "claude-x")
    texto = await cerebro.pensar("instrucción", respaldo="respaldo")

    assert texto == "hola"


async def test_pensar_si_la_llamada_falla_no_registra_uso(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = _RespuestaFalsa(500, {"error": "boom"})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _ClienteFalso(respuesta))

    reportados: list[int] = []

    async def _registrar(tokens: int) -> None:
        reportados.append(tokens)

    cerebro = CerebroAnthropic("sk-ant-test", "claude-x", registrar_uso=_registrar)
    texto = await cerebro.pensar("instrucción", respaldo="respaldo")

    assert texto == "respaldo"
    assert reportados == []
