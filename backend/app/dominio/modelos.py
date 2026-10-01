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
class EventoAgente:
    """Contrato congelado del WebSocket: {agent, status, msg} más metadatos opcionales."""

    agent: str
    status: Estado
    msg: str
    ts: str = field(default_factory=_ahora_iso)
    run_id: str | None = None
    artifacts: list[str] = field(default_factory=list)


@dataclass
class CredencialVercel:
    """Resultado de un intercambio OAuth exitoso con Vercel."""

    access_token: str
    team_id: str | None = None
    creado_en: datetime | None = None


@dataclass
class CredencialRender:
    """API key de Render, ya verificada contra su API antes de guardarse."""

    api_key: str
    creado_en: datetime | None = None


@dataclass
class CredencialAnthropic:
    """API key de la consola de Anthropic (console.anthropic.com), ya
    verificada con una llamada real antes de guardarse. No tiene relación con
    una sesión de claude.ai o Claude Code: es una credencial de la API,
    facturada aparte.
    """

    api_key: str
    creado_en: datetime | None = None


@dataclass
class UsoAnthropic:
    """Contador local de tokens consumidos por Orquesta contra un límite que
    define quien lo usa. Anthropic no expone el gasto ni el cupo real de una
    cuenta a través de una API key normal (eso requiere una Admin API key y
    sigue sin dar un "% de plan"), así que este límite no viene de la cuenta:
    lo fija el usuario acá para saber cuándo frenar.
    """

    limite_tokens: int
    tokens_usados: int = 0
    actualizado_en: datetime | None = None

    def porcentaje(self) -> float:
        if self.limite_tokens <= 0:
            return 0.0
        return min(100.0, (self.tokens_usados / self.limite_tokens) * 100)
