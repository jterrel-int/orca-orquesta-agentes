"""Precio por millón de tokens (entrada, salida) en USD, por modelo.

Los de Claude son las tarifas de la API de Anthropic vigentes a la fecha de
este archivo. Cualquier otro proveedor (DeepSeek, OpenAI, …) se agrega con
TARIFAS_EXTRA en .env — sin tarifa, el costo se informa como desconocido en
vez de inventarlo.
"""

from __future__ import annotations

import json
import logging

from ..config import config

log = logging.getLogger(__name__)

TARIFAS_BASE: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _tarifas_extra() -> dict[str, tuple[float, float]]:
    """TARIFAS_EXTRA='{"deepseek-chat": [0.27, 1.10]}' — USD por millón."""
    if not config.tarifas_extra.strip():
        return {}
    try:
        crudo = json.loads(config.tarifas_extra)
        return {str(k): (float(v[0]), float(v[1])) for k, v in crudo.items()}
    except (ValueError, TypeError, IndexError, AttributeError):
        log.warning("TARIFAS_EXTRA no es un JSON válido {modelo: [entrada, salida]}; se ignora")
        return {}


def costo_usd(modelo: str, tokens_entrada: int, tokens_salida: int) -> float | None:
    tarifa = _tarifas_extra().get(modelo) or TARIFAS_BASE.get(modelo)
    if tarifa is None:
        return None
    entrada, salida = tarifa
    return round((tokens_entrada * entrada + tokens_salida * salida) / 1_000_000, 6)
