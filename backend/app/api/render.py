"""Conexión con Render. Sin OAuth de su lado: se pega una API key y se
verifica contra su API antes de guardarla — nunca se guarda una inválida.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..adaptadores.persistencia_sqlalchemy import (
    RepositorioCredencialRenderSQLAlchemy,
    obtener_sesion,
)
from ..adaptadores.render_api import buscar_servicio, obtener_usuario
from ..config import config
from ..dominio.errores import CredencialInvalida
from ..dominio.modelos import CredencialRender

router = APIRouter(prefix="/api/render", tags=["render"])


class ConexionCrear(BaseModel):
    api_key: str = Field(min_length=1)


async def _info_cuenta(api_key: str) -> dict[str, Any]:
    usuario = await obtener_usuario(api_key)
    servicio = await buscar_servicio(api_key, config.render_service_name)
    return {
        "conectado": True,
        "email": usuario.get("email"),
        "nombre": usuario.get("name"),
        "servicio_url": (servicio or {}).get("serviceDetails", {}).get("url"),
        "servicio_suspendido": (servicio or {}).get("suspended") if servicio else None,
    }


@router.post("/conexion")
async def conectar(
    datos: ConexionCrear, sesion: AsyncSession = Depends(obtener_sesion)
) -> dict[str, Any]:
    try:
        info = await _info_cuenta(datos.api_key)
    except CredencialInvalida as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await RepositorioCredencialRenderSQLAlchemy(sesion).guardar(
        CredencialRender(api_key=datos.api_key)
    )
    return info


@router.get("/estado")
async def estado(sesion: AsyncSession = Depends(obtener_sesion)) -> dict[str, Any]:
    credencial = await RepositorioCredencialRenderSQLAlchemy(sesion).obtener()
    if credencial is None:
        return {"conectado": False}

    try:
        return await _info_cuenta(credencial.api_key)
    except CredencialInvalida:
        # La key guardada dejó de servir (rotada, revocada). No la borramos
        # solos: se lo decimos al panel y que la persona decida reconectar.
        return {"conectado": False, "advertencia": "La API key guardada ya no es válida"}


@router.delete("/conexion", status_code=204)
async def desconectar(sesion: AsyncSession = Depends(obtener_sesion)) -> None:
    await RepositorioCredencialRenderSQLAlchemy(sesion).eliminar()
