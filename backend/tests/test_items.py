"""CRUD de Item contra SQLite en memoria, a través de ServicioItems."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adaptadores.persistencia_sqlalchemy import Base, RepositorioItemsSQLAlchemy
from app.dominio.errores import ItemNoEncontrado
from app.dominio.servicios import ServicioItems


@pytest.fixture
async def servicio() -> AsyncIterator[ServicioItems]:
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)

    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as sesion:
        yield ServicioItems(RepositorioItemsSQLAlchemy(sesion))
    await motor.dispose()


async def test_crear_y_listar(servicio: ServicioItems) -> None:
    creado = await servicio.crear("primero")
    assert creado.id is not None

    items = await servicio.listar()
    assert [i.name for i in items] == ["primero"]


async def test_actualizar(servicio: ServicioItems) -> None:
    creado = await servicio.crear("original")
    assert creado.id is not None

    actualizado = await servicio.actualizar(creado.id, "nuevo nombre")
    assert actualizado.name == "nuevo nombre"


async def test_eliminar(servicio: ServicioItems) -> None:
    creado = await servicio.crear("temporal")
    assert creado.id is not None

    await servicio.eliminar(creado.id)
    assert await servicio.listar() == []


async def test_obtener_inexistente_lanza_error(servicio: ServicioItems) -> None:
    with pytest.raises(ItemNoEncontrado):
        await servicio.obtener(9999)


async def test_actualizar_inexistente_lanza_error(servicio: ServicioItems) -> None:
    with pytest.raises(ItemNoEncontrado):
        await servicio.actualizar(9999, "no existe")


async def test_eliminar_inexistente_lanza_error(servicio: ServicioItems) -> None:
    with pytest.raises(ItemNoEncontrado):
        await servicio.eliminar(9999)
