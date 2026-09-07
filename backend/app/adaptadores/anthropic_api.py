"""Verifica una API key de Anthropic antes de guardarla — nunca se guarda una
que no funciona. Es una clave de la consola de la API (console.anthropic.com,
facturada por token), no la sesión de claude.ai o Claude Code: no hay forma
soportada de reutilizar esa sesión desde un backend propio, así que este es
el único camino real para que la app llame a Claude de verdad.
"""

from __future__ import annotations

import httpx

from ..dominio.errores import CredencialInvalida

URL_MENSAJES = "https://api.anthropic.com/v1/messages"


async def verificar_api_key(api_key: str, modelo: str) -> None:
    """Hace una llamada mínima (1 token de salida) solo para confirmar que la
    key es válida. Lanza CredencialInvalida si no lo es.
    """
    cabeceras = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    cuerpo = {
        "model": modelo,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hola"}],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as cliente:
            r = await cliente.post(URL_MENSAJES, json=cuerpo, headers=cabeceras)
    except httpx.HTTPError as e:
        raise CredencialInvalida(f"No se pudo contactar a la API de Anthropic: {e}") from e

    if r.status_code == 401:
        raise CredencialInvalida("La API key de Anthropic no es válida")
    if r.status_code == 404:
        raise CredencialInvalida(f"El modelo configurado no existe o no está disponible: {modelo}")
    if r.status_code >= 400:
        raise CredencialInvalida(f"Anthropic respondió {r.status_code}: {r.text[:200]}")
