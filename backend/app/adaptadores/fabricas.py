"""Cableado: qué implementación concreta de cada puerto se usa, según config.

Los agentes reciben su puerto por constructor y, si no se les da uno, lo piden
aquí. Es el único lugar que decide entre implementaciones — ni los agentes ni
el orquestador tienen un `if` sobre config.brain o config.deploy_enabled.
"""

from __future__ import annotations

import logging

from ..config import config
from ..dominio.puertos import Cerebro, Desplegador
from .cerebro_anthropic import CerebroAnthropic
from .cerebro_guionado import CerebroGuionado
from .despliegue_simulado import DespliegueSimulado
from .despliegue_vercel import DespliegueVercel

log = logging.getLogger(__name__)


def construir_cerebro() -> Cerebro:
    """Si falta la clave, cae a guionado y lo avisa."""
    if config.brain == "anthropic":
        if not config.anthropic_api_key:
            log.warning("BRAIN=anthropic pero falta ANTHROPIC_API_KEY; se usa el guionado")
            return CerebroGuionado()
        return CerebroAnthropic(config.anthropic_api_key, config.anthropic_model)
    return CerebroGuionado()


def construir_desplegador() -> Desplegador:
    if config.deploy_enabled:
        return DespliegueVercel()
    return DespliegueSimulado()
