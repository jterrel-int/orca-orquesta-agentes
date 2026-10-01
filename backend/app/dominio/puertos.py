"""Puertos: los Protocol que separan el dominio de la infraestructura.

Cada uno tiene (al menos) dos adaptadores reales en app/adaptadores/. El
cableado — qué implementación concreta se usa — vive en adaptadores/fabricas.py
y en config.py; el dominio solo conoce estas formas.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from .fabrica import (
    Encargo,
    MetricaEtapa,
    RegistroBitacora,
    RespuestaMedida,
    ResultadoComando,
)
from .modelos import CredencialAnthropic, EventoAgente, UsoAnthropic

EmisorLinea = Callable[[str], Awaitable[None]]


@runtime_checkable
class Cerebro(Protocol):
    """Produce texto a partir de una instrucción y un contexto."""

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str: ...


@runtime_checkable
class Desplegador(Protocol):
    """Corre el despliegue de un encargo de la fábrica (hoy: GitHub, real o
    simulado) y reporta cada línea de salida por `on_linea`.

    Devuelve la URL de producción si la hay, o None. Lanza DespliegueFallido
    si el despliegue no se completó.
    """

    async def ejecutar(self, on_linea: EmisorLinea) -> str | None: ...


@runtime_checkable
class PublicadorEventos(Protocol):
    async def publicar(self, evento: EventoAgente) -> None: ...


@runtime_checkable
class RepositorioCredencialAnthropic(Protocol):
    """Guarda la API key de Anthropic pegada desde Configuración.
    `construir_cerebro()` la prefiere sobre ANTHROPIC_API_KEY cuando hay una
    guardada.
    """

    async def guardar(self, credencial: CredencialAnthropic) -> None: ...
    async def obtener(self) -> CredencialAnthropic | None: ...
    async def eliminar(self) -> None: ...


@runtime_checkable
class RepositorioUsoAnthropic(Protocol):
    """Guarda el contador de tokens usados y el límite local (ver
    UsoAnthropic). No refleja el gasto real de la cuenta de Anthropic — eso no
    es consultable con una API key normal — sino un tope que define el
    usuario para saber cuándo frenar.
    """

    async def obtener(self) -> UsoAnthropic | None: ...
    async def establecer_limite(self, limite_tokens: int) -> UsoAnthropic: ...
    async def sumar_tokens(self, tokens: int) -> UsoAnthropic: ...


@runtime_checkable
class CerebroMedido(Protocol):
    """Un Cerebro que además informa cuántos tokens usó y cuánto costaron.
    Separado de Cerebro a propósito: la fábrica lo aprovecha cuando está, y
    cuando no (claude-cli) estima — los agentes históricos no cambian.
    """

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida: ...


@runtime_checkable
class RepositorioEncargos(Protocol):
    async def guardar(self, encargo: Encargo) -> None: ...
    async def obtener(self, encargo_id: str) -> Encargo | None: ...
    async def listar(self) -> list[Encargo]: ...


@runtime_checkable
class BitacoraInmutable(Protocol):
    """Solo agrega y lee. No hay actualizar ni borrar: ni en el puerto, ni en
    el adaptador, ni en la base (un trigger de SQLite lo impide).
    """

    async def registrar(
        self, encargo_id: str, agente: str, accion: str, evidencia: dict[str, Any]
    ) -> RegistroBitacora: ...
    async def listar(self, encargo_id: str | None = None) -> list[RegistroBitacora]: ...


@runtime_checkable
class RepositorioMetricas(Protocol):
    async def registrar(self, metrica: MetricaEtapa) -> None: ...
    async def listar(self, encargo_id: str | None = None) -> list[MetricaEtapa]: ...


@runtime_checkable
class EjecutorPruebas(Protocol):
    """Corre un comando de verificación dentro del espacio de trabajo de un
    encargo. Dos adaptadores: subproceso local y contenedor Docker aislado.
    """

    async def ejecutar(
        self, directorio: str, comando: list[str], timeout_s: float
    ) -> ResultadoComando: ...
