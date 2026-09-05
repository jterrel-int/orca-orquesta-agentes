"""Entidades del dominio: dataclasses puras, sin pydantic ni ORM.

Nada aquí importa fastapi, sqlalchemy, httpx ni app.config — eso lo verifica
backend/tests/test_arquitectura.py. Los adaptadores traducen estas dataclasses
a lo que necesite cada borde (filas de SQLAlchemy, esquemas de FastAPI, JSON).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Estado = Literal["pending", "running", "done", "error"]


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Item:
    id: int | None
    name: str
    creado_en: datetime | None = None


@dataclass
class EventoAgente:
    """Contrato congelado del WebSocket: {agent, status, msg} más metadatos opcionales."""

    agent: str
    status: Estado
    msg: str
    ts: str = field(default_factory=_ahora_iso)
    run_id: str | None = None
    artifacts: list[str] = field(default_factory=list)


@dataclass
class EstadoAgente:
    """Estado consolidado de un agente dentro de una corrida."""

    agent: str
    status: Estado = "pending"
    ultimo_msg: str = ""
    duracion_s: float | None = None


@dataclass
class ResumenCorrida:
    run_id: str
    status: Literal["running", "done", "error"]
    agentes: list[EstadoAgente]
    iniciado_en: str
    terminado_en: str | None = None
