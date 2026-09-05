"""Intercambia el `code` de una instalación OAuth de Vercel por un access token.

Referencia: https://vercel.com/docs/integrations/create-integration/vercel-api-integrations
El `code` que Vercel manda al callback vale una sola vez y expira a los 30
minutos; por eso este intercambio no se reintenta ni se cachea.
"""

from __future__ import annotations

import httpx

from ..config import config
from ..dominio.errores import OAuthFallido
from ..dominio.modelos import CredencialVercel

URL_INTERCAMBIO = "https://api.vercel.com/v2/oauth/access_token"


async def intercambiar_code(code: str) -> CredencialVercel:
    if not config.vercel_client_id or not config.vercel_client_secret:
        raise OAuthFallido("Falta VERCEL_CLIENT_ID o VERCEL_CLIENT_SECRET en el backend")

    datos = {
        "client_id": config.vercel_client_id,
        "client_secret": config.vercel_client_secret,
        "code": code,
        "redirect_uri": config.vercel_oauth_redirect_uri,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as cliente:
            r = await cliente.post(URL_INTERCAMBIO, data=datos)
            r.raise_for_status()
            cuerpo = r.json()
    except httpx.HTTPError as e:
        raise OAuthFallido(f"El intercambio con Vercel falló: {e}") from e

    access_token = cuerpo.get("access_token")
    if not access_token:
        raise OAuthFallido("Vercel no devolvió un access_token")

    return CredencialVercel(access_token=access_token, team_id=cuerpo.get("team_id"))
