"""Casos de uso. Reciben sus puertos por constructor y no saben nada de HTTP,
SQL ni subprocesos.
"""

from __future__ import annotations

from .errores import ItemNoEncontrado
from .modelos import Item, Lado, TareaBacklog
from .puertos import RepositorioBacklog, RepositorioItems


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


class ServicioBacklog:
    def __init__(self, repositorio: RepositorioBacklog) -> None:
        self._repo = repositorio

    def listar(self) -> list[TareaBacklog]:
        return self._repo.listar()

    def agregar(self, titulo: str, cuerpo: str, lado: Lado) -> TareaBacklog:
        tarea = TareaBacklog(id=self._siguiente_id(lado), titulo=titulo, cuerpo=cuerpo, lado=lado)
        self._repo.agregar(tarea)
        return tarea

    def _siguiente_id(self, lado: Lado) -> str:
        numeros = [
            int(t.id.split("-", 1)[1])
            for t in self._repo.listar()
            if t.lado == lado and "-" in t.id and t.id.split("-", 1)[1].isdigit()
        ]
        return f"{lado}-{max(numeros, default=0) + 1:02d}"
