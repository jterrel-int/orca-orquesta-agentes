"""Adaptador de persistencia: SQLAlchemy async sobre SQLite (aiosqlite).

Base declarativa, motor y sesiones compartidas, más las credenciales y el
contador de uso de Configuración. Las tablas de la fábrica (encargos,
bitácora, métricas, caché del LLM) viven en persistencia_fabrica.py y
cache_llm.py sobre esta misma Base.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..config import config
from ..dominio.modelos import (
    CredencialAnthropic,
    CredencialRender,
    CredencialVercel,
    UsoAnthropic,
)


class Base(DeclarativeBase):
    """Base declarativa de SQLAlchemy 2.0 para todos los modelos ORM."""


def _ahora() -> datetime:
    return datetime.now(UTC)


class CredencialVercelORM(Base):
    """Una sola fila (id=1): este MVP conecta una cuenta de Vercel a la vez."""

    __tablename__ = "credenciales_vercel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_token: Mapped[str] = mapped_column(String(200), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    def a_dominio(self) -> CredencialVercel:
        return CredencialVercel(
            access_token=self.access_token, team_id=self.team_id, creado_en=self.creado_en
        )


class CredencialRenderORM(Base):
    """Misma idea que CredencialVercelORM: una sola fila, id=1."""

    __tablename__ = "credenciales_render"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_key: Mapped[str] = mapped_column(String(200), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    def a_dominio(self) -> CredencialRender:
        return CredencialRender(api_key=self.api_key, creado_en=self.creado_en)


class CredencialAnthropicORM(Base):
    """Misma idea que CredencialVercelORM/CredencialRenderORM: una sola fila,
    id=1 — este MVP usa una única API key de Anthropic para todo el proceso.
    """

    __tablename__ = "credenciales_anthropic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_key: Mapped[str] = mapped_column(String(200), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    def a_dominio(self) -> CredencialAnthropic:
        return CredencialAnthropic(api_key=self.api_key, creado_en=self.creado_en)


class UsoAnthropicORM(Base):
    """Una sola fila (id=1): contador global de tokens usados en este proceso
    contra el límite local que fijó el usuario (ver dominio.modelos.UsoAnthropic).
    """

    __tablename__ = "uso_anthropic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    limite_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_usados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    def a_dominio(self) -> UsoAnthropic:
        return UsoAnthropic(
            limite_tokens=self.limite_tokens,
            tokens_usados=self.tokens_usados,
            actualizado_en=self.actualizado_en,
        )


motor = create_async_engine(config.database_url, echo=False, future=True)

FabricaSesion = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)


async def crear_tablas() -> None:
    """Crea el esquema si no existe. Para un MVP alcanza; en producción, migraciones."""
    # Import tardío: persistencia_fabrica importa Base de este módulo. Además
    # de evitar el ciclo, garantiza que sus tablas estén registradas en
    # Base.metadata antes del create_all.
    from . import cache_llm  # noqa: F401 — registra su tabla en Base.metadata
    from .persistencia_fabrica import proteger_bitacora

    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)
        await proteger_bitacora(conexion)


async def obtener_sesion() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI. Una sesión por request, cerrada siempre."""
    async with FabricaSesion() as sesion:
        yield sesion


class RepositorioCredencialVercelSQLAlchemy:
    """Token OAuth de Vercel guardado desde Configuración."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def guardar(self, credencial: CredencialVercel) -> None:
        fila = await self._sesion.get(CredencialVercelORM, 1)
        if fila is None:
            fila = CredencialVercelORM(id=1)
            self._sesion.add(fila)
        fila.access_token = credencial.access_token
        fila.team_id = credencial.team_id
        await self._sesion.commit()

    async def obtener(self) -> CredencialVercel | None:
        fila = await self._sesion.get(CredencialVercelORM, 1)
        return fila.a_dominio() if fila else None

    async def eliminar(self) -> None:
        fila = await self._sesion.get(CredencialVercelORM, 1)
        if fila:
            await self._sesion.delete(fila)
            await self._sesion.commit()


class RepositorioCredencialRenderSQLAlchemy:
    """Sin puerto propio: solo lo usa api/render.py, no hay lógica de dominio
    que necesite probarse contra un doble.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def guardar(self, credencial: CredencialRender) -> None:
        fila = await self._sesion.get(CredencialRenderORM, 1)
        if fila is None:
            fila = CredencialRenderORM(id=1)
            self._sesion.add(fila)
        fila.api_key = credencial.api_key
        await self._sesion.commit()

    async def obtener(self) -> CredencialRender | None:
        fila = await self._sesion.get(CredencialRenderORM, 1)
        return fila.a_dominio() if fila else None

    async def eliminar(self) -> None:
        fila = await self._sesion.get(CredencialRenderORM, 1)
        if fila:
            await self._sesion.delete(fila)
            await self._sesion.commit()


class RepositorioCredencialAnthropicSQLAlchemy:
    """Implementa dominio.puertos.RepositorioCredencialAnthropic."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def guardar(self, credencial: CredencialAnthropic) -> None:
        fila = await self._sesion.get(CredencialAnthropicORM, 1)
        if fila is None:
            fila = CredencialAnthropicORM(id=1)
            self._sesion.add(fila)
        fila.api_key = credencial.api_key
        await self._sesion.commit()

    async def obtener(self) -> CredencialAnthropic | None:
        fila = await self._sesion.get(CredencialAnthropicORM, 1)
        return fila.a_dominio() if fila else None

    async def eliminar(self) -> None:
        fila = await self._sesion.get(CredencialAnthropicORM, 1)
        if fila:
            await self._sesion.delete(fila)
            await self._sesion.commit()


class RepositorioUsoAnthropicSQLAlchemy:
    """Implementa dominio.puertos.RepositorioUsoAnthropic."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self) -> UsoAnthropic | None:
        fila = await self._sesion.get(UsoAnthropicORM, 1)
        return fila.a_dominio() if fila else None

    async def establecer_limite(self, limite_tokens: int) -> UsoAnthropic:
        fila = await self._sesion.get(UsoAnthropicORM, 1)
        if fila is None:
            fila = UsoAnthropicORM(id=1, limite_tokens=limite_tokens, tokens_usados=0)
            self._sesion.add(fila)
        else:
            fila.limite_tokens = limite_tokens
        fila.actualizado_en = _ahora()
        await self._sesion.commit()
        await self._sesion.refresh(fila)
        return fila.a_dominio()

    async def sumar_tokens(self, tokens: int) -> UsoAnthropic:
        fila = await self._sesion.get(UsoAnthropicORM, 1)
        if fila is None:
            fila = UsoAnthropicORM(id=1, limite_tokens=0, tokens_usados=0)
            self._sesion.add(fila)
        fila.tokens_usados += tokens
        fila.actualizado_en = _ahora()
        await self._sesion.commit()
        await self._sesion.refresh(fila)
        return fila.a_dominio()
