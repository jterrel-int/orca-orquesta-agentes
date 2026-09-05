"""Contrato que todo agente cumple.

La separación clave: un agente sabe *qué* hacer, no *cuándo* ni *junto a quién*.
Eso lo decide el orquestador. Un agente nunca llama a otro agente.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..dominio.modelos import Estado, EventoAgente

Emisor = Callable[[EventoAgente], Awaitable[None]]


@dataclass
class ContextoCorrida:
    """Lo que un agente recibe para trabajar.

    `datos` es el canal entre agentes: el BackendAgent deja ahí los endpoints
    que generó y el FrontendAgent los lee. Nunca se llaman entre sí.
    """

    run_id: str
    emitir: Emisor
    datos: dict = field(default_factory=dict)


@dataclass
class ResultadoAgente:
    agent: str
    status: Estado
    msg: str
    duracion_s: float
    artifacts: list[str] = field(default_factory=list)


class Agente(ABC):
    """Clase base. Subclasea e implementa `ejecutar`."""

    name: str = "agente"

    async def log(self, ctx: ContextoCorrida, msg: str, status: Estado = "running",
                  artifacts: list[str] | None = None) -> None:
        await ctx.emitir(
            EventoAgente(
                agent=self.name,
                status=status,
                msg=msg,
                run_id=ctx.run_id,
                artifacts=artifacts or [],
            )
        )

    @abstractmethod
    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        """Hace el trabajo. Devuelve las rutas de los artefactos producidos.

        Puede lanzar excepciones: `correr` las convierte en un resultado de error.
        """

    async def correr(self, ctx: ContextoCorrida) -> ResultadoAgente:
        """Envoltura que mide, emite inicio/fin y captura fallos.

        Los agentes concretos no repiten este manejo de errores.
        """
        inicio = time.perf_counter()
        await self.log(ctx, f"{self.name} iniciado", status="running")
        try:
            artefactos = await self.ejecutar(ctx)
        except Exception as e:  # noqa: BLE001 — la frontera de fallo es aquí a propósito
            duracion = time.perf_counter() - inicio
            msg = f"{type(e).__name__}: {e}"
            await self.log(ctx, msg, status="error")
            return ResultadoAgente(self.name, "error", msg, duracion)

        duracion = time.perf_counter() - inicio
        msg = f"{self.name} terminado en {duracion:.1f}s"
        await self.log(ctx, msg, status="done", artifacts=artefactos)
        return ResultadoAgente(self.name, "done", msg, duracion, artefactos)
