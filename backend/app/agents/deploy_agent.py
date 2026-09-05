"""Agente 3: despliega el frontend a Vercel a través del puerto Desplegador.

Este es el único agente con efectos fuera del repositorio. El adaptador que
usa —real o simulado— lo decide adaptadores/fabricas.py según
DEPLOY_ENABLED; el agente no sabe cuál de los dos le tocó.
"""

from __future__ import annotations

from ..adaptadores.fabricas import construir_desplegador
from ..config import config
from ..dominio.puertos import Desplegador
from .base import Agente, ContextoCorrida


class DeployAgent(Agente):
    name = "deploy"

    def __init__(self, desplegador: Desplegador | None = None) -> None:
        self._desplegador = desplegador or construir_desplegador()

    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        async def on_linea(texto: str) -> None:
            await self.log(ctx, texto)

        url_produccion = await self._desplegador.ejecutar(on_linea)

        if not config.deploy_enabled:
            ctx.datos["deploy"] = "omitido"
            return []

        if url_produccion:
            ctx.datos["url_produccion"] = url_produccion
            await self.log(ctx, f"Desplegado en {url_produccion}")

        ctx.datos["deploy"] = "ok"
        return [url_produccion] if url_produccion else []
