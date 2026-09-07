"""Conexión con Anthropic. Se pega una API key de console.anthropic.com y se
verifica con una llamada real antes de guardarla — nunca se guarda una que no
funciona. No tiene nada que ver con una sesión de claude.ai o Claude Code:
esas no son credenciales reutilizables por un backend propio.

No usa `from __future__ import annotations`: este módulo tiene una ruta
`status_code=204` con retorno `-> None`, y FastAPI infiere mal el
response_model si esa anotación llega como string (ver CLAUDE.md).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..adaptadores.anthropic_api import verificar_api_key
from ..adaptadores.persistencia_sqlalchemy import (
    RepositorioCredencialAnthropicSQLAlchemy,
    obtener_sesion,
)
from ..config import config
from ..dominio.errores import CredencialInvalida
from ..dominio.modelos import CredencialAnthropic

router = APIRouter(prefix="/api/anthropic", tags=["anthropic"])


class ConexionCrear(BaseModel):
    api_key: str = Field(min_length=1)


def _enmascarar(api_key: str) -> str:
    """Nunca se devuelve la key completa — ni al conectar ni al consultar el
    estado. Los últimos 4 caracteres alcanzan para reconocerla sin exponerla.
    """
    return f"···{api_key[-4:]}" if len(api_key) > 4 else "···"


@router.post("/conexion")
async def conectar(
    datos: ConexionCrear, sesion: AsyncSession = Depends(obtener_sesion)
) -> dict[str, Any]:
    try:
        await verificar_api_key(datos.api_key, config.anthropic_model)
    except CredencialInvalida as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await RepositorioCredencialAnthropicSQLAlchemy(sesion).guardar(
        CredencialAnthropic(api_key=datos.api_key)
    )
    return {
        "conectado": True,
        "modelo": config.anthropic_model,
        "clave": _enmascarar(datos.api_key),
    }


@router.get("/estado")
async def estado(sesion: AsyncSession = Depends(obtener_sesion)) -> dict[str, Any]:
    credencial = await RepositorioCredencialAnthropicSQLAlchemy(sesion).obtener()
    if credencial is None:
        return {"conectado": False, "modelo": config.anthropic_model}

    return {
        "conectado": True,
        "modelo": config.anthropic_model,
        "clave": _enmascarar(credencial.api_key),
    }


@router.delete("/conexion", status_code=204)
async def desconectar(sesion: AsyncSession = Depends(obtener_sesion)) -> None:
    await RepositorioCredencialAnthropicSQLAlchemy(sesion).eliminar()
