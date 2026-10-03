"""CerebroOpenAICompatible (DeepSeek por defecto) y el cálculo de costo."""

from __future__ import annotations

import httpx
import pytest

from app.adaptadores import tarifas
from app.adaptadores.cerebro_openai_compatible import CerebroOpenAICompatible
from app.config import config


class _Respuesta:
    def __init__(self, cuerpo: object, status: int = 200) -> None:
        self._cuerpo = cuerpo
        self.status_code = status

    def json(self) -> object:
        return self._cuerpo

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class _Cliente:
    peticiones: list[dict[str, object]] = []

    def __init__(self, respuesta: _Respuesta) -> None:
        self._respuesta = respuesta

    async def __aenter__(self) -> _Cliente:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, **kwargs: object) -> _Respuesta:
        _Cliente.peticiones.append({"url": url, **kwargs})
        return self._respuesta


def _parchar(monkeypatch: pytest.MonkeyPatch, respuesta: _Respuesta) -> None:
    _Cliente.peticiones = []
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: _Cliente(respuesta))


async def test_devuelve_texto_y_consumo_con_tarifa_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "tarifas_extra", '{"deepseek-chat": [0.5, 2.0]}')
    _parchar(
        monkeypatch,
        _Respuesta(
            {
                "model": "deepseek-chat",
                "choices": [{"message": {"content": "hola"}}],
                "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
            }
        ),
    )
    cerebro = CerebroOpenAICompatible("clave", "deepseek-chat", "https://api.deepseek.com/")
    r = await cerebro.pensar_medido("instrucción", respaldo="respaldo")

    assert r.texto == "hola"
    assert r.consumo.tokens_entrada == 1_000_000
    assert r.consumo.costo_usd == 1.5
    peticion = _Cliente.peticiones[0]
    assert peticion["url"] == "https://api.deepseek.com/chat/completions"
    assert peticion["headers"] == {"Authorization": "Bearer clave"}


async def test_sin_tarifa_el_costo_es_desconocido_y_un_fallo_usa_el_respaldo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "tarifas_extra", "")
    _parchar(monkeypatch, _Respuesta({"choices": [{"message": {"content": "x"}}]}))
    r = await CerebroOpenAICompatible("k", "modelo-raro", "https://x").pensar_medido("i")
    assert r.consumo.costo_usd is None

    _parchar(monkeypatch, _Respuesta({}, status=500))
    r = await CerebroOpenAICompatible("k", "m", "https://x").pensar_medido("i", respaldo="plan B")
    assert r.texto == "plan B"


def test_tarifas_de_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "tarifas_extra", "no es json")
    assert tarifas.costo_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.0
    assert tarifas.costo_usd("claude-haiku-4-5", 2_000, 1_000) == 0.007
    assert tarifas.costo_usd("desconocido", 10, 10) is None
