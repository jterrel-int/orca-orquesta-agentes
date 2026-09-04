"""Motor async de SQLAlchemy sobre SQLite (aiosqlite)."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import config
from ..models.base import Base

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
