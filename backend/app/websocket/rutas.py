"""Endpoint WebSocket. Un único canal: /ws"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..api.seguridad import websocket_permitido
from .manager import gestor

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def canal_eventos(ws: WebSocket) -> None:
    if not websocket_permitido(ws):
        # 1008 = violación de política. Antes de aceptar: no se envía nada.
        await ws.close(code=1008)
        return
    await gestor.conectar(ws)
    try:
        while True:
            # No esperamos mensajes del cliente; leemos solo para detectar el
            # cierre de la conexión.
            await ws.receive_text()
    except WebSocketDisconnect:
        gestor.desconectar(ws)
    except Exception:  # noqa: BLE001
        gestor.desconectar(ws)
