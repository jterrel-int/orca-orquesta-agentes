"""Adaptador determinista del puerto Cerebro. Sin red, sin clave. Por defecto."""

from __future__ import annotations

from ..dominio.fabrica import Consumo, RespuestaMedida


class CerebroGuionado:
    """Devuelve el respaldo tal cual.

    Es el modo por defecto: un demo en vivo no debería depender de una API
    externa ni de una clave que puede no estar configurada.
    """

    nombre = "scripted"

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return respaldo

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        return RespuestaMedida(respaldo, Consumo("guionado", 0, 0, 0.0))
