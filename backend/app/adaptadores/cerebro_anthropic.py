"""Adaptador real del puerto Cerebro contra la API de mensajes de Anthropic."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from ..dominio.fabrica import Consumo, RespuestaMedida
from .reintentos_http import post_con_reintentos
from .tarifas import costo_usd

log = logging.getLogger(__name__)

RegistradorDeUso = Callable[[int], Awaitable[None]]


class CerebroAnthropic:
    """Si la llamada falla por cualquier motivo, cae al respaldo determinista en
    lugar de tumbar la corrida. Un agente sin red debe degradar, no explotar.
    """

    nombre = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        api_key: str,
        modelo: str,
        registrar_uso: RegistradorDeUso | None = None,
        *,
        max_tokens: int = 16000,
        timeout_s: float = 300.0,
        reintentos: int = 2,
    ) -> None:
        self._api_key = api_key
        self._modelo = modelo
        # El Implementador devuelve archivos completos dentro de un JSON: con
        # el tope viejo de 2000 tokens la respuesta llegaba cortada, el JSON no
        # se podía leer y el encargo caía a la plantilla de respaldo.
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._reintentos = reintentos
        # Anthropic no expone el gasto de la cuenta a una API key normal; este
        # callback es cómo Orquesta lleva su propio contador de tokens (ver
        # dominio.modelos.UsoAnthropic) sin que este adaptador conozca SQLAlchemy.
        self._registrar_uso = registrar_uso

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return (await self.pensar_medido(instruccion, contexto, respaldo=respaldo)).texto

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        cuerpo = {
            "model": self._modelo,
            "max_tokens": self._max_tokens,
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
            r = await post_con_reintentos(
                self.URL,
                cuerpo=cuerpo,
                cabeceras=cabeceras,
                timeout_s=self._timeout_s,
                reintentos=self._reintentos,
            )
            datos = r.json()
            if datos.get("stop_reason") == "max_tokens":
                log.warning(
                    "Cerebro Anthropic: respuesta cortada en max_tokens=%s; si el JSON no "
                    "se puede leer se usará el respaldo (sube CEREBRO_MAX_TOKENS)",
                    self._max_tokens,
                )
            partes = [
                b.get("text", "") for b in datos.get("content", []) if b.get("type") == "text"
            ]
            texto = "\n".join(p for p in partes if p).strip()

            uso = datos.get("usage") or {}
            entrada = int(uso.get("input_tokens", 0))
            salida = int(uso.get("output_tokens", 0))
            if self._registrar_uso is not None and (entrada + salida):
                await self._registrar_uso(entrada + salida)

            # Se cobra el modelo que respondió, no el que se pidió.
            modelo = str(datos.get("model") or self._modelo)
            consumo = Consumo(modelo, entrada, salida, costo_usd(modelo, entrada, salida))
            return RespuestaMedida(texto or respaldo, consumo)
        except Exception as e:  # noqa: BLE001
            log.warning("Cerebro Anthropic falló (%s); se usa el respaldo", e)
            return RespuestaMedida(respaldo, Consumo(self._modelo))
