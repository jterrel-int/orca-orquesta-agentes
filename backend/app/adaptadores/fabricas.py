"""Cableado: qué implementación concreta de cada puerto se usa, según config.

Los agentes reciben su puerto por constructor y, si no se les da uno, lo piden
aquí. Es el único lugar que decide entre implementaciones — ni los agentes ni
el orquestador tienen un `if` sobre config.brain o config.deploy_enabled.
"""

from __future__ import annotations

import logging

from ..config import config
from ..dominio.puertos import (
    Cerebro,
    Desplegador,
    RepositorioCredencialAnthropic,
    RepositorioCredencialVercel,
)
from .cerebro_anthropic import CerebroAnthropic
from .cerebro_guionado import CerebroGuionado
from .despliegue_simulado import DespliegueSimulado
from .despliegue_vercel import DespliegueVercel

log = logging.getLogger(__name__)


async def _api_key_anthropic(
    credenciales: RepositorioCredencialAnthropic | None,
) -> tuple[str | None, str | None]:
    """Devuelve (api_key, fuente) — la key guardada desde Configuración tiene
    prioridad sobre ANTHROPIC_API_KEY, igual que `construir_desplegador()` con
    el token OAuth de Vercel. `fuente` es para mostrar en /api/health, nunca
    la key en sí.
    """
    if credenciales is None:
        from .persistencia_sqlalchemy import FabricaSesion, RepositorioCredencialAnthropicSQLAlchemy

        async with FabricaSesion() as sesion:
            credencial = await RepositorioCredencialAnthropicSQLAlchemy(sesion).obtener()
    else:
        credencial = await credenciales.obtener()

    if credencial is not None:
        return credencial.api_key, "guardada en Configuración"
    if config.anthropic_api_key:
        return config.anthropic_api_key, "variable de entorno ANTHROPIC_API_KEY"
    return None, None


async def construir_cerebro(
    credenciales: RepositorioCredencialAnthropic | None = None,
) -> Cerebro:
    """Si no hay ninguna API key (ni guardada ni por variable de entorno), cae
    a guionado y lo avisa.
    """
    api_key, fuente = await _api_key_anthropic(credenciales)
    if api_key is None:
        if config.brain == "anthropic":
            log.warning("BRAIN=anthropic pero falta una API key de Anthropic; se usa el guionado")
        return CerebroGuionado()
    log.info("Cerebro Anthropic activo (%s)", fuente)
    return CerebroAnthropic(api_key, config.anthropic_model)


async def estado_cerebro(
    credenciales: RepositorioCredencialAnthropic | None = None,
) -> dict[str, str | None]:
    """Para /api/health y Configuración: qué cerebro está activo ahora mismo y
    de dónde sale la clave — nunca la clave en sí.
    """
    api_key, fuente = await _api_key_anthropic(credenciales)
    if api_key is None:
        return {"activo": "scripted", "modelo": None, "fuente": None}
    return {"activo": "anthropic", "modelo": config.anthropic_model, "fuente": fuente}


async def construir_desplegador(
    credenciales: RepositorioCredencialVercel | None = None,
) -> Desplegador:
    """Si hay un token OAuth guardado (ver api/vercel.py), tiene prioridad sobre
    VERCEL_TOKEN. `credenciales` es inyectable para probar esa preferencia sin
    tocar SQLite de verdad.
    """
    if not config.deploy_enabled:
        return DespliegueSimulado()

    if credenciales is None:
        from .persistencia_sqlalchemy import FabricaSesion, RepositorioCredencialVercelSQLAlchemy

        async with FabricaSesion() as sesion:
            credencial = await RepositorioCredencialVercelSQLAlchemy(sesion).obtener()
    else:
        credencial = await credenciales.obtener()

    token = credencial.access_token if credencial else config.vercel_token
    return DespliegueVercel(token=token)
