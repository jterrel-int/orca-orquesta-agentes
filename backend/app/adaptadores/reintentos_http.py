"""POST con reintentos para los cerebros que hablan HTTP.

Un 429 (límite de tasa), un 529 (Anthropic sobrecargado), un 5xx o un corte
de red son pasajeros: sin reintento, el cerebro caía al respaldo (la
plantilla) y el encargo terminaba preguntando por un "problema del entorno"
que un segundo intento habría resuelto solo. Los errores del pedido (400,
401, 404…) no se reintentan: repetirlos da lo mismo.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

REINTENTABLES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})
_ESPERA_MAXIMA_S = 30.0


def _espera(respuesta: Any, intento: int, base_s: float) -> float:
    """Respeta `retry-after` si el proveedor lo manda; si no, backoff exponencial."""
    cabeceras = getattr(respuesta, "headers", None) or {}
    try:
        pedida = float(cabeceras.get("retry-after", ""))
    except (TypeError, ValueError):
        pedida = 0.0
    return min(_ESPERA_MAXIMA_S, pedida or base_s * (2**intento))


async def post_con_reintentos(
    url: str,
    *,
    cuerpo: dict[str, Any],
    cabeceras: dict[str, str],
    timeout_s: float,
    reintentos: int = 2,
    espera_base_s: float = 1.0,
) -> Any:
    """Devuelve la respuesta exitosa o lanza la última excepción."""
    for intento in range(reintentos + 1):
        ultimo = intento >= reintentos
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as cliente:
                r = await cliente.post(url, json=cuerpo, headers=cabeceras)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if ultimo:
                raise
            espera = _espera(None, intento, espera_base_s)
            log.warning("POST %s falló (%s); reintento en %.1fs", url, e, espera)
            await asyncio.sleep(espera)
            continue
        if r.status_code in REINTENTABLES and not ultimo:
            espera = _espera(r, intento, espera_base_s)
            log.warning("POST %s respondió %s; reintento en %.1fs", url, r.status_code, espera)
            await asyncio.sleep(espera)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("inalcanzable")  # pragma: no cover
