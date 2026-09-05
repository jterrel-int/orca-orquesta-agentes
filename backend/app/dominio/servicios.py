"""Casos de uso. Reciben sus puertos por constructor y no saben nada de HTTP,
SQL ni subprocesos.
"""

from __future__ import annotations

from .errores import ItemNoEncontrado
from .modelos import Item
from .puertos import RepositorioItems


class ServicioItems:
    def __init__(self, repositorio: RepositorioItems) -> None:
        self._repo = repositorio

    async def listar(self) -> list[Item]:
        return await self._repo.listar()

    async def crear(self, name: str) -> Item:
        return await self._repo.crear(name)

    async def obtener(self, item_id: int) -> Item:
        item = await self._repo.obtener(item_id)
        if item is None:
            raise ItemNoEncontrado(item_id)
        return item

    async def actualizar(self, item_id: int, name: str) -> Item:
        item = await self._repo.actualizar(item_id, name)
        if item is None:
            raise ItemNoEncontrado(item_id)
        return item

    async def eliminar(self, item_id: int) -> None:
        borrado = await self._repo.eliminar(item_id)
        if not borrado:
            raise ItemNoEncontrado(item_id)
