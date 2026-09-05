"""Adaptador real del puerto Cerebro contra la API de mensajes de Anthropic."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class CerebroAnthropic:
    """Si la llamada falla por cualquier motivo, cae al respaldo determinista en
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
            partes = [
                b.get("text", "") for b in datos.get("content", []) if b.get("type") == "text"
            ]
            texto = "\n".join(p for p in partes if p).strip()
            return texto or respaldo
        except Exception as e:  # noqa: BLE001
            log.warning("Cerebro Anthropic falló (%s); se usa el respaldo", e)
            return respaldo
