"""Disparo y consulta de corridas de agentes."""

import asyncio
import dataclasses
import inspect
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..adaptadores.bus_memoria import bus
from ..agents.casos_de_uso import CASOS_DE_USO, CasoDeUso
from ..dominio.modelos import ResumenCorrida
from ..orchestrator.orquestador import orquestador

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["corridas"])


class LanzarCorridaEntrada(BaseModel):
    """Body opcional de POST /api/run. Ausente o caso_de_uso=None es el caso
    "items" histórico.
    """

    caso_de_uso: str | None = None


# Ganchos que se ejecutan al terminar una corrida. main.py registra aquí el
# montaje del router generado. Evita que este módulo importe la app y con ello
# un ciclo de importación. El valor de retorno no importa; por eso el tipo es
# object y no None: montar_router_generado devuelve bool y no hace falta envolverlo.
# Un gancho puede ser sync o async (devolver un objeto awaitable); _correr_seguro
# lo espera si hace falta.
_ganchos_post_corrida: list[Callable[[], object]] = []


def registrar_post_corrida(fn: Callable[[], object]) -> None:
    _ganchos_post_corrida.append(fn)


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def lanzar_corrida(entrada: LanzarCorridaEntrada | None = None) -> dict[str, Any]:
    """Lanza el pipeline en segundo plano y responde de inmediato.

    El progreso viaja por el WebSocket, no por esta respuesta: mantener la
    petición abierta durante todo el pipeline sería frágil y no aportaría nada.
    Body opcional `{"caso_de_uso": "..." | null}`; ausente o null es el caso
    "items" de siempre.
    """
    if orquestador.corriendo:
        raise HTTPException(status_code=409, detail="Ya hay una corrida en curso")

    caso_de_uso = entrada.caso_de_uso if entrada else None
    ids_validos = {c.id for c in CASOS_DE_USO}
    if caso_de_uso is not None and caso_de_uso not in ids_validos:
        raise HTTPException(status_code=422, detail=f"caso_de_uso desconocido: {caso_de_uso}")

    bus.limpiar_historial()
    asyncio.create_task(_correr_seguro(caso_de_uso))
    return {"status": "accepted", "detalle": "Corrida lanzada; escucha /ws para el progreso"}


async def _correr_seguro(caso_de_uso: str | None = None) -> None:
    try:
        await orquestador.ejecutar(caso_de_uso)
    except Exception:  # noqa: BLE001
        log.exception("La corrida terminó con una excepción no controlada")
    finally:
        # Los endpoints que acaba de generar el BackendAgent se montan solos.
        for gancho in _ganchos_post_corrida:
            try:
                resultado = gancho()
                if inspect.isawaitable(resultado):
                    await resultado
            except Exception:  # noqa: BLE001
                log.exception("Falló un gancho posterior a la corrida")


@router.get("/run/status", response_model=ResumenCorrida | None)
async def estado_corrida() -> ResumenCorrida | None:
    return orquestador.resumen


@router.get("/events")
async def historial_eventos() -> list[dict[str, Any]]:
    """Historial en memoria, para clientes que no usan WebSocket."""
    return [dataclasses.asdict(e) for e in bus.historial()]


@router.get("/casos-de-uso", response_model=list[CasoDeUso])
async def listar_casos_de_uso() -> list[CasoDeUso]:
    """Metadata de los casos de uso seleccionables, para que el frontend no la
    hardcodee.
    """
    return CASOS_DE_USO
