"""Disparo y consulta de corridas de agentes."""

import asyncio
import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from ..models.eventos import ResumenCorrida
from ..orchestrator.eventos import bus
from ..orchestrator.orquestador import orquestador

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["corridas"])

# Ganchos que se ejecutan al terminar una corrida. main.py registra aquí el
# montaje del router generado. Evita que este módulo importe la app y con ello
# un ciclo de importación.
_ganchos_post_corrida: list[Callable[[], None]] = []


def registrar_post_corrida(fn: Callable[[], None]) -> None:
    _ganchos_post_corrida.append(fn)


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def lanzar_corrida() -> dict:
    """Lanza el pipeline en segundo plano y responde de inmediato.

    El progreso viaja por el WebSocket, no por esta respuesta: mantener la
    petición abierta durante todo el pipeline sería frágil y no aportaría nada.
    """
    if orquestador.corriendo:
        raise HTTPException(status_code=409, detail="Ya hay una corrida en curso")

    bus.limpiar_historial()
    asyncio.create_task(_correr_seguro())
    return {"status": "accepted", "detalle": "Corrida lanzada; escucha /ws para el progreso"}


async def _correr_seguro() -> None:
    try:
        await orquestador.ejecutar()
    except Exception:  # noqa: BLE001
        log.exception("La corrida terminó con una excepción no controlada")
    finally:
        # Los endpoints que acaba de generar el BackendAgent se montan solos.
        for gancho in _ganchos_post_corrida:
            try:
                gancho()
            except Exception:  # noqa: BLE001
                log.exception("Falló un gancho posterior a la corrida")


@router.get("/run/status", response_model=ResumenCorrida | None)
async def estado_corrida() -> ResumenCorrida | None:
    return orquestador.resumen


@router.get("/events")
async def historial_eventos() -> list[dict]:
    """Historial en memoria, para clientes que no usan WebSocket."""
    return [e.model_dump() for e in bus.historial()]
