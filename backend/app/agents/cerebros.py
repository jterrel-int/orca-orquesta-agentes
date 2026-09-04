"""El punto exacto donde un agente determinista se convierte en uno con LLM.

Los agentes no llaman a ninguna API: le piden a su `Cerebro` que produzca el
contenido. Cambiar BRAIN=anthropic en el entorno cambia de determinista a LLM
sin tocar una línea de los agentes ni del orquestador.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import httpx

from ..config import config

log = logging.getLogger(__name__)


@runtime_checkable
class Cerebro(Protocol):
    """Produce texto a partir de una instrucción y un contexto."""

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        ...


class CerebroGuionado:
    """Devuelve el respaldo tal cual. Determinista, sin red, sin clave.

    Es el modo por defecto: un demo en vivo no debería depender de una API
    externa ni de una clave que puede no estar configurada.
    """

    nombre = "scripted"

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return respaldo


class CerebroAnthropic:
    """Implementación real contra la API de mensajes.

    Si la llamada falla por cualquier motivo, cae al respaldo determinista en
    lugar de tumbar la corrida. Un agente sin red debe degradar, no explotar.
    """

    nombre = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, modelo: str) -> None:
        self._api_key = api_key
        self._modelo = modelo

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        cuerpo = {
            "model": self._modelo,
            "max_tokens": 2000,
            "messages": [
                {
                    "role": "user",
                    "content": f"{instruccion}\n\n<contexto>\n{contexto}\n</contexto>",
                }
            ],
        }
        cabeceras = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as cliente:
                r = await cliente.post(self.URL, json=cuerpo, headers=cabeceras)
                r.raise_for_status()
                datos = r.json()
            partes = [b.get("text", "") for b in datos.get("content", []) if b.get("type") == "text"]
            texto = "\n".join(p for p in partes if p).strip()
            return texto or respaldo
        except Exception as e:  # noqa: BLE001
            log.warning("Cerebro Anthropic falló (%s); se usa el respaldo", e)
            return respaldo


def construir_cerebro() -> Cerebro:
    """Fábrica según configuración. Si falta la clave, cae a guionado y lo avisa."""
    if config.brain == "anthropic":
        if not config.anthropic_api_key:
            log.warning("BRAIN=anthropic pero falta ANTHROPIC_API_KEY; se usa el guionado")
            return CerebroGuionado()
        return CerebroAnthropic(config.anthropic_api_key, config.anthropic_model)
    return CerebroGuionado()
