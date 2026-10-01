"""Integración opcional con Prefect: observabilidad y tablero, no orquestación.

Excepción explícita a la regla de "asyncio puro" de CLAUDE.md, decidida por
una persona: el Líder sigue decidiendo el orden, los reintentos y el
paralelismo con asyncio. Prefect solo *observa*: con FABRICA_ORQUESTADOR=prefect,
cada encargo aparece como un flow run y cada etapa como un task run en la UI
de Prefect (`prefect server start` → http://127.0.0.1:4200), con su estado,
duración y logs.

Apagado (el valor por defecto) o sin el paquete instalado, estas funciones
solo esperan la corrutina: cero dependencias, cero diferencia de conducta.
Prefect se importa recién al usarlo, nunca al importar este módulo.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")


def prefect_disponible() -> bool:
    return importlib.util.find_spec("prefect") is not None


async def en_flujo(
    activo: bool, nombre: str, nombre_corrida: str, trabajo: Callable[[], Awaitable[T]]
) -> T:
    """Corre `trabajo` como un flow de Prefect si `activo`; si no, tal cual."""
    if not activo:
        return await trabajo()
    from prefect import flow

    async def cuerpo() -> T:
        return await trabajo()

    # Como llamada y no como decorador: con Prefect sin instalar, mypy lo ve
    # como Any y un decorador Any borraría el tipo de la función.
    flujo = flow(
        name=nombre, flow_run_name=nombre_corrida, log_prints=False, validate_parameters=False
    )(cuerpo)
    resultado: T = await flujo()
    return resultado


async def en_tarea(
    activo: bool, nombre: str, nombre_corrida: str, trabajo: Callable[[], Awaitable[T]]
) -> T:
    """Corre `trabajo` como un task de Prefect si `activo`. Sin caché de
    Prefect: los argumentos (una corrutina ya creada) no son hasheables, y
    la caché que importa es la de respuestas del LLM, no la de Prefect.
    """
    if not activo:
        return await trabajo()
    from prefect import task
    from prefect.cache_policies import NO_CACHE

    async def cuerpo() -> T:
        return await trabajo()

    tarea = task(name=nombre, task_run_name=nombre_corrida, cache_policy=NO_CACHE, retries=0)(
        cuerpo
    )
    resultado: T = await tarea()
    return resultado
