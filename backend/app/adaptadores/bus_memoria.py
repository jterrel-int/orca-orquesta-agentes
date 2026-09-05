"""Adaptador del puerto PublicadorEventos: bus en memoria, pub/sub sobre asyncio.

Desacopla a los agentes del transporte. Un agente publica; quien quiera escucha.
Hoy escucha el WebSocket; mañana podría escuchar un logger o una cola.

Un único consumidor del bus retransmite a todos los clientes conectados, en vez
de una suscripción por cliente. Así el bus no crece con el número de pestañas
abiertas (ver websocket/manager.py).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from ..dominio.modelos import EventoAgente

log = logging.getLogger(__name__)


class BusEventosMemoria:
    def __init__(self, tam_cola: int = 512) -> None:
        self._suscriptores: set[asyncio.Queue[EventoAgente]] = set()
        self._tam_cola = tam_cola
        self._historial: list[EventoAgente] = []
        self._max_historial = 400

    async def publicar(self, evento: EventoAgente) -> None:
        self._historial.append(evento)
        if len(self._historial) > self._max_historial:
            del self._historial[: len(self._historial) - self._max_historial]

        for cola in list(self._suscriptores):
            try:
                cola.put_nowait(evento)
            except asyncio.QueueFull:
                # Un cliente lento no puede frenar a los agentes ni tumbar el bus.
                log.warning("Cola de suscriptor llena; se descarta el evento")

    def historial(self) -> list[EventoAgente]:
        return list(self._historial)

    def limpiar_historial(self) -> None:
        self._historial.clear()

    async def suscribir(self) -> AsyncIterator[EventoAgente]:
        cola: asyncio.Queue[EventoAgente] = asyncio.Queue(maxsize=self._tam_cola)
        self._suscriptores.add(cola)
        try:
            while True:
                yield await cola.get()
        finally:
            self._suscriptores.discard(cola)

    @property
    def n_suscriptores(self) -> int:
        return len(self._suscriptores)


bus = BusEventosMemoria()
