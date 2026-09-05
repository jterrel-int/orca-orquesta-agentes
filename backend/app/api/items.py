"""Adaptador de entrada HTTP para Item: traduce HTTP <-> ServicioItems.

Existe para que el frontend tenga contra qué trabajar antes de que los agentes
corran. El BackendAgent genera un router equivalente en app/generated/; ambos
comparten prefijo y FastAPI resuelve por orden de inclusión.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..adaptadores.persistencia_sqlalchemy import RepositorioItemsSQLAlchemy, obtener_sesion
from ..dominio.errores import ItemNoEncontrado
from ..dominio.modelos import Item
from ..dominio.servicios import ServicioItems

router = APIRouter(prefix="/api/items", tags=["items"])


class ItemCrear(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ItemActualizar(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ItemLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    creado_en: datetime


def item_a_leer(item: Item) -> ItemLeer:
    """Traduce el dominio a la forma que responde la API. Reusado por el router generado."""
    # id y creado_en son Optional en el dominio (un Item podría no estar persistido
    # todavía), pero todo lo que sale del repositorio ya pasó por la base de datos.
    assert item.id is not None
    assert item.creado_en is not None
    return ItemLeer(id=item.id, name=item.name, creado_en=item.creado_en)


async def obtener_servicio_items(sesion: AsyncSession = Depends(obtener_sesion)) -> ServicioItems:
    return ServicioItems(RepositorioItemsSQLAlchemy(sesion))


@router.get("", response_model=list[ItemLeer])
async def listar(servicio: ServicioItems = Depends(obtener_servicio_items)) -> list[ItemLeer]:
    return [item_a_leer(i) for i in await servicio.listar()]


@router.post("", response_model=ItemLeer, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: ItemCrear, servicio: ServicioItems = Depends(obtener_servicio_items)
) -> ItemLeer:
    return item_a_leer(await servicio.crear(datos.name))


@router.get("/{item_id}", response_model=ItemLeer)
async def obtener(
    item_id: int, servicio: ServicioItems = Depends(obtener_servicio_items)
) -> ItemLeer:
    try:
        return item_a_leer(await servicio.obtener(item_id))
    except ItemNoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{item_id}", response_model=ItemLeer)
async def actualizar(
    item_id: int,
    datos: ItemActualizar,
    servicio: ServicioItems = Depends(obtener_servicio_items),
) -> ItemLeer:
    try:
        return item_a_leer(await servicio.actualizar(item_id, datos.name))
    except ItemNoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(item_id: int, servicio: ServicioItems = Depends(obtener_servicio_items)) -> None:
    try:
        await servicio.eliminar(item_id)
    except ItemNoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
