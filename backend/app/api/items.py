"""CRUD de Item escrito a mano.

Existe para que el frontend tenga contra qué trabajar antes de que los agentes
corran. El BackendAgent genera un router equivalente en app/generated/; ambos
comparten prefijo y FastAPI resuelve por orden de inclusión.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import obtener_sesion
from ..models.item import Item, ItemActualizar, ItemCrear, ItemLeer

router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("", response_model=list[ItemLeer])
async def listar(sesion: AsyncSession = Depends(obtener_sesion)) -> list[Item]:
    resultado = await sesion.execute(select(Item).order_by(Item.id.desc()))
    return list(resultado.scalars().all())


@router.post("", response_model=ItemLeer, status_code=status.HTTP_201_CREATED)
async def crear(datos: ItemCrear, sesion: AsyncSession = Depends(obtener_sesion)) -> Item:
    item = Item(name=datos.name)
    sesion.add(item)
    await sesion.commit()
    await sesion.refresh(item)
    return item


@router.get("/{item_id}", response_model=ItemLeer)
async def obtener(item_id: int, sesion: AsyncSession = Depends(obtener_sesion)) -> Item:
    item = await sesion.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    return item


@router.put("/{item_id}", response_model=ItemLeer)
async def actualizar(
    item_id: int, datos: ItemActualizar, sesion: AsyncSession = Depends(obtener_sesion)
) -> Item:
    item = await sesion.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    item.name = datos.name
    await sesion.commit()
    await sesion.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(item_id: int, sesion: AsyncSession = Depends(obtener_sesion)) -> None:
    item = await sesion.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    await sesion.delete(item)
    await sesion.commit()
