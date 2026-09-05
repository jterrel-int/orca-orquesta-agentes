"""Llamadas a la API de Render. Sin OAuth de su lado: la API key se pega a
mano y se verifica acá antes de guardarla — nunca se guarda una que no
funciona.

Referencia: https://api-docs.render.com
"""

from __future__ import annotations

from typing import Any

import httpx

from ..dominio.errores import CredencialInvalida

BASE_URL = "https://api.render.com/v1"


def _cabeceras(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


async def obtener_usuario(api_key: str) -> dict[str, Any]:
    """Verifica la API key contra GET /v1/users. Lanza CredencialInvalida si no sirve."""
    try:
        async with httpx.AsyncClient(timeout=15) as cliente:
            r = await cliente.get(f"{BASE_URL}/users", headers=_cabeceras(api_key))
    except httpx.HTTPError as e:
        raise CredencialInvalida(f"No se pudo contactar a Render: {e}") from e

    if r.status_code == 401:
        raise CredencialInvalida("La API key de Render no es válida")
    r.raise_for_status()
    resultado: dict[str, Any] = r.json()
    return resultado


async def buscar_servicio(api_key: str, nombre: str) -> dict[str, Any] | None:
    """Busca un servicio por nombre exacto. Devuelve su `service` o None si no existe."""
    try:
        async with httpx.AsyncClient(timeout=15) as cliente:
            r = await cliente.get(
                f"{BASE_URL}/services",
                headers=_cabeceras(api_key),
                params={"name": nombre, "limit": 1},
            )
    except httpx.HTTPError as e:
        raise CredencialInvalida(f"No se pudo contactar a Render: {e}") from e

    if r.status_code == 401:
        raise CredencialInvalida("La API key de Render no es válida")
    r.raise_for_status()
    resultados: list[dict[str, Any]] = r.json()
    if not resultados:
        return None
    servicio: dict[str, Any] = resultados[0]["service"]
    return servicio
