"""Contrato de los mensajes que viajan por el WebSocket.

El formato pedido es {agent, status, msg}. Se agregan campos opcionales que el
dashboard usa y que un cliente antiguo puede ignorar sin romperse.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Estado = Literal["pending", "running", "done", "error"]


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventoAgente(BaseModel):
    agent: str
    status: Estado
    msg: str
    ts: str = Field(default_factory=_ahora_iso)
    run_id: str | None = None
    # Artefactos producidos por el agente (rutas relativas al repo).
    artifacts: list[str] = Field(default_factory=list)


class EstadoAgente(BaseModel):
    """Estado consolidado de un agente dentro de una corrida."""

    agent: str
    status: Estado = "pending"
    ultimo_msg: str = ""
    duracion_s: float | None = None


class ResumenCorrida(BaseModel):
    run_id: str
    status: Literal["running", "done", "error"]
    agentes: list[EstadoAgente]
    iniciado_en: str
    terminado_en: str | None = None
