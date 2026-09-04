"""Gestor de conexiones WebSocket.

Un único consumidor del bus retransmite a todos los clientes conectados, en vez
de una suscripción por cliente. Así el bus no crece con el número de pestañas
abiertas.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from ..models.eventos import EventoAgente
from ..orchestrator.eventos import bus

log = logging.getLogger(__name__)


class GestorConexiones:
    def __init__(self) -> None:
        self._conexiones: set[WebSocket] = set()
        self._tarea: asyncio.Task | None = None

    async def conectar(self, ws: WebSocket) -> None:
        await ws.accept()
        self._conexiones.add(ws)
        # Al conectar, el cliente recibe lo ya ocurrido: una pestaña abierta a
        # mitad de una corrida no se queda mirando una pantalla vacía.
        for evento in bus.historial():
            await self._enviar(ws, evento)

    def desconectar(self, ws: WebSocket) -> None:
        self._conexiones.discard(ws)

    async def difundir(self, evento: EventoAgente) -> None:
        muertas: list[WebSocket] = []
        for ws in list(self._conexiones):
            if not await self._enviar(ws, evento):
                muertas.append(ws)
        for ws in muertas:
            self.desconectar(ws)

    async def _enviar(self, ws: WebSocket, evento: EventoAgente) -> bool:
        try:
            await ws.send_text(evento.model_dump_json())
            return True
        except Exception:  # noqa: BLE001 — cliente caído, no es un error del servidor
            return False

    async def iniciar_retransmision(self) -> None:
        if self._tarea and not self._tarea.done():
            return
        self._tarea = asyncio.create_task(self._bucle())

    async def detener_retransmision(self) -> None:
        if self._tarea:
            self._tarea.cancel()
            try:
                await self._tarea
            except asyncio.CancelledError:
                pass
            self._tarea = None

    async def _bucle(self) -> None:
        async for evento in bus.suscribir():
            await self.difundir(evento)

    @property
    def n_conexiones(self) -> int:
        return len(self._conexiones)


gestor = GestorConexiones()
