"""Adaptador de persistencia: SQLAlchemy async sobre SQLite (aiosqlite).

Implementa el puerto RepositorioItems. Nadie fuera de este módulo conoce
SQLAlchemy ni la fila ORM; el resto de la app trabaja con dominio.modelos.Item.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..config import config
from ..dominio.modelos import Item


class Base(DeclarativeBase):
    """Base declarativa de SQLAlchemy 2.0 para todos los modelos ORM."""


def _ahora() -> datetime:
    return datetime.now(UTC)


class ItemORM(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    def a_dominio(self) -> Item:
        return Item(id=self.id, name=self.name, creado_en=self.creado_en)


motor = create_async_engine(config.database_url, echo=False, future=True)

FabricaSesion = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)


async def crear_tablas() -> None:
    """Crea el esquema si no existe. Para un MVP alcanza; en producción, migraciones."""
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)


async def obtener_sesion() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI. Una sesión por request, cerrada siempre."""
    async with FabricaSesion() as sesion:
        yield sesion


class RepositorioItemsSQLAlchemy:
    """Implementa dominio.puertos.RepositorioItems contra SQLite."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self) -> list[Item]:
        resultado = await self._sesion.execute(select(ItemORM).order_by(ItemORM.id.desc()))
        return [fila.a_dominio() for fila in resultado.scalars().all()]

    async def crear(self, name: str) -> Item:
        fila = ItemORM(name=name)
        self._sesion.add(fila)
        await self._sesion.commit()
        await self._sesion.refresh(fila)
        return fila.a_dominio()

    async def obtener(self, item_id: int) -> Item | None:
        fila = await self._sesion.get(ItemORM, item_id)
        return fila.a_dominio() if fila else None

    async def actualizar(self, item_id: int, name: str) -> Item | None:
        fila = await self._sesion.get(ItemORM, item_id)
        if fila is None:
            return None
        fila.name = name
        await self._sesion.commit()
        await self._sesion.refresh(fila)
        return fila.a_dominio()

    async def eliminar(self, item_id: int) -> bool:
        fila = await self._sesion.get(ItemORM, item_id)
        if fila is None:
            return False
        await self._sesion.delete(fila)
        await self._sesion.commit()
        return True
