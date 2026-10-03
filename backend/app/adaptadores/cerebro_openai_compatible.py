"""Adaptador del puerto Cerebro contra cualquier API compatible con el formato
de chat completions de OpenAI — DeepSeek por defecto.

La idea que motiva este adaptador: cuando las especificaciones están bien
acotadas y el harness valida todo, un modelo más barato alcanza para buena
parte de las etapas. Cambiar de proveedor es cambiar .env, no los agentes.
"""

from __future__ import annotations

import logging

from ..dominio.fabrica import Consumo, RespuestaMedida
from .reintentos_http import post_con_reintentos
from .tarifas import costo_usd

log = logging.getLogger(__name__)


class CerebroOpenAICompatible:
    nombre = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        modelo: str,
        base_url: str,
        *,
        max_tokens: int = 8192,
        timeout_s: float = 300.0,
        reintentos: int = 2,
    ) -> None:
        self._api_key = api_key
        self._modelo = modelo
        self._url = base_url.rstrip("/") + "/chat/completions"
        # DeepSeek admite hasta 8192 de salida; más que eso lo rechaza con 400.
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._reintentos = reintentos

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return (await self.pensar_medido(instruccion, contexto, respaldo=respaldo)).texto

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        cuerpo = {
            "model": self._modelo,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": f"{instruccion}\n\n<contexto>\n{contexto}\n</contexto>",
                }
            ],
        }
        cabeceras = {"Authorization": f"Bearer {self._api_key}"}
        try:
            r = await post_con_reintentos(
                self._url,
                cuerpo=cuerpo,
                cabeceras=cabeceras,
                timeout_s=self._timeout_s,
                reintentos=self._reintentos,
            )
            datos = r.json()
            opciones = datos.get("choices") or []
            texto = ""
            if opciones and opciones[0].get("finish_reason") == "length":
                log.warning(
                    "Cerebro %s: respuesta cortada en max_tokens=%s (sube "
                    "OPENAI_COMPAT_MAX_TOKENS si el modelo lo admite)",
                    self._modelo,
                    self._max_tokens,
                )
            if opciones:
                texto = str((opciones[0].get("message") or {}).get("content") or "").strip()
            uso = datos.get("usage") or {}
            entrada = int(uso.get("prompt_tokens", 0))
            salida = int(uso.get("completion_tokens", 0))
            modelo = str(datos.get("model") or self._modelo)
            consumo = Consumo(modelo, entrada, salida, costo_usd(modelo, entrada, salida))
            return RespuestaMedida(texto or respaldo, consumo)
        except Exception as e:  # noqa: BLE001
            log.warning("Cerebro %s falló (%s); se usa el respaldo", self._modelo, e)
            return RespuestaMedida(respaldo, Consumo(self._modelo))
