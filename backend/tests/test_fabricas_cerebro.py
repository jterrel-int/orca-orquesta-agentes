"""construir_cerebro()/estado_cerebro(): la API key guardada desde
Configuración tiene prioridad sobre ANTHROPIC_API_KEY; sin ninguna de las dos
cae a guionado.
"""

from __future__ import annotations

import pytest

from app.adaptadores.cerebro_anthropic import CerebroAnthropic
from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.adaptadores.fabricas import construir_cerebro, estado_cerebro
from app.config import config
from app.dominio.modelos import CredencialAnthropic


class _CredencialesFalsas:
    """Doble del puerto RepositorioCredencialAnthropic, en memoria."""

    def __init__(self, guardada: CredencialAnthropic | None = None) -> None:
        self._guardada = guardada

    async def guardar(self, credencial: CredencialAnthropic) -> None:
        self._guardada = credencial

    async def obtener(self) -> CredencialAnthropic | None:
        return self._guardada

    async def eliminar(self) -> None:
        self._guardada = None


async def test_sin_credencial_guardada_ni_env_cae_a_guionado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "anthropic_api_key", None)

    cerebro = await construir_cerebro(_CredencialesFalsas())

    assert isinstance(cerebro, CerebroGuionado)
    assert (await estado_cerebro(_CredencialesFalsas()))["activo"] == "scripted"


async def test_usa_la_variable_de_entorno_si_no_hay_credencial_guardada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "anthropic_api_key", "sk-ant-del-env")

    cerebro = await construir_cerebro(_CredencialesFalsas())

    assert isinstance(cerebro, CerebroAnthropic)
    estado = await estado_cerebro(_CredencialesFalsas())
    assert estado["activo"] == "anthropic"
    assert estado["fuente"] == "variable de entorno ANTHROPIC_API_KEY"


async def test_credencial_guardada_tiene_prioridad_sobre_la_variable_de_entorno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "anthropic_api_key", "sk-ant-del-env")
    credenciales = _CredencialesFalsas(CredencialAnthropic(api_key="sk-ant-guardada"))

    cerebro = await construir_cerebro(credenciales)

    assert isinstance(cerebro, CerebroAnthropic)
    estado = await estado_cerebro(credenciales)
    assert estado["fuente"] == "guardada en Configuración"


async def test_estado_nunca_expone_la_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    credenciales = _CredencialesFalsas(CredencialAnthropic(api_key="sk-ant-secreta-de-verdad"))

    estado = await estado_cerebro(credenciales)

    assert "sk-ant-secreta-de-verdad" not in str(estado)
