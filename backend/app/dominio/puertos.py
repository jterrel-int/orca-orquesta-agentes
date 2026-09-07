"""Puertos: los Protocol que separan el dominio de la infraestructura.

Cada uno tiene (al menos) dos adaptadores reales en app/adaptadores/. El
cableado — qué implementación concreta se usa — vive en adaptadores/fabricas.py
y en config.py; el dominio solo conoce estas formas.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from .modelos import CredencialAnthropic, CredencialVercel, EventoAgente, Item, TareaBacklog

EmisorLinea = Callable[[str], Awaitable[None]]


@runtime_checkable
class RepositorioItems(Protocol):
    async def listar(self) -> list[Item]: ...
    async def crear(self, name: str) -> Item: ...
    async def obtener(self, item_id: int) -> Item | None: ...
    async def actualizar(self, item_id: int, name: str) -> Item | None: ...
    async def eliminar(self, item_id: int) -> bool: ...


@runtime_checkable
class Cerebro(Protocol):
    """Produce texto a partir de una instrucción y un contexto."""

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str: ...


@runtime_checkable
class Desplegador(Protocol):
    """Corre el despliegue y reporta cada línea de salida por `on_linea`.

    Devuelve la URL de producción si la hay, o None. Lanza DespliegueFallido
    si el despliegue no se completó.
    """

    async def ejecutar(self, on_linea: EmisorLinea) -> str | None: ...


@runtime_checkable
class PublicadorEventos(Protocol):
    async def publicar(self, evento: EventoAgente) -> None: ...


@runtime_checkable
class RepositorioBacklog(Protocol):
    """Lectura y escritura de docs/BACKLOG.md. Sin async: es I/O local chico,
    no algo por lo que valga la pena hacer esperar al event loop.
    """

    def listar(self) -> list[TareaBacklog]: ...
    def agregar(self, tarea: TareaBacklog) -> None: ...


@runtime_checkable
class RepositorioCredencialVercel(Protocol):
    """Guarda el token OAuth de Vercel. `construir_desplegador()` lo prefiere
    sobre VERCEL_TOKEN cuando hay uno guardado — de ahí que sea un puerto: hace
    falta poder probar esa preferencia sin tocar SQLite de verdad.
    """

    async def guardar(self, credencial: CredencialVercel) -> None: ...
    async def obtener(self) -> CredencialVercel | None: ...
    async def eliminar(self) -> None: ...


@runtime_checkable
class RepositorioCredencialAnthropic(Protocol):
    """Guarda la API key de Anthropic pegada desde Configuración.
    `construir_cerebro()` la prefiere sobre ANTHROPIC_API_KEY cuando hay una
    guardada — mismo criterio que Vercel con su token OAuth.
    """

    async def guardar(self, credencial: CredencialAnthropic) -> None: ...
    async def obtener(self) -> CredencialAnthropic | None: ...
    async def eliminar(self) -> None: ...
