"""Conexión OAuth con Vercel: iniciar el flujo, atender el callback, consultar
y cortar la conexión.

El botón "Conectar con Vercel" del panel abre `/oauth/iniciar` en una ventana
emergente; Vercel redirige a `/oauth/callback` con el `code`, este endpoint lo
canjea y cierra la ventana solo. El panel detecta el cierre y refresca su
estado — ver frontend/components/ConexionVercel.tsx.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..adaptadores.oauth_vercel import intercambiar_code
from ..adaptadores.persistencia_sqlalchemy import (
    RepositorioCredencialVercelSQLAlchemy,
    obtener_sesion,
)
from ..config import config
from ..dominio.errores import OAuthFallido

router = APIRouter(prefix="/api/vercel", tags=["vercel"])

# Una sola instalación pendiente a la vez — mismo criterio que "una corrida a
# la vez" en el orquestador: este es un panel de un solo usuario local.
_estado_pendiente: str | None = None


@router.get("/oauth/iniciar")
async def iniciar_oauth() -> RedirectResponse:
    global _estado_pendiente

    if not config.vercel_integration_slug or not config.vercel_client_id:
        raise HTTPException(
            status_code=500,
            detail="Falta VERCEL_INTEGRATION_SLUG o VERCEL_CLIENT_ID en el backend",
        )

    _estado_pendiente = secrets.token_urlsafe(24)
    url = f"https://vercel.com/integrations/{config.vercel_integration_slug}/new?state={_estado_pendiente}"
    return RedirectResponse(url)


@router.get("/oauth/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    sesion: AsyncSession = Depends(obtener_sesion),
) -> HTMLResponse:
    global _estado_pendiente

    if state != _estado_pendiente:
        return HTMLResponse(
            "<p>El estado no coincide; iniciá la conexión de nuevo desde el panel.</p>",
            status_code=400,
        )
    _estado_pendiente = None

    try:
        credencial = await intercambiar_code(code)
    except OAuthFallido as e:
        return HTMLResponse(f"<p>No se pudo conectar con Vercel: {e}</p>", status_code=502)

    await RepositorioCredencialVercelSQLAlchemy(sesion).guardar(credencial)

    return HTMLResponse(
        "<p>Conectado. Esta ventana se cierra sola…</p><script>window.close()</script>"
    )


@router.get("/estado")
async def estado(sesion: AsyncSession = Depends(obtener_sesion)) -> dict[str, object]:
    credencial = await RepositorioCredencialVercelSQLAlchemy(sesion).obtener()
    return {
        "conectado": credencial is not None,
        "team_id": credencial.team_id if credencial else None,
    }


@router.delete("/conexion", status_code=204)
async def desconectar(sesion: AsyncSession = Depends(obtener_sesion)) -> None:
    await RepositorioCredencialVercelSQLAlchemy(sesion).eliminar()
