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
    RepositorioUsoAnthropicSQLAlchemy,
    obtener_sesion,
)
from ..config import config
from ..dominio.errores import CredencialInvalida
from ..dominio.modelos import CredencialAnthropic, UsoAnthropic

router = APIRouter(prefix="/api/anthropic", tags=["anthropic"])


class ConexionCrear(BaseModel):
    api_key: str = Field(min_length=1)


class LimiteUsoCrear(BaseModel):
    """Tope de tokens que el usuario define para saber cuándo frenar.

    No es el cupo real de la cuenta de Anthropic — eso no es consultable con
    una API key normal — sino un número que Orquesta usa para avisar por
    umbrales (10%, 20%, …) mientras acumula el uso de sus propias llamadas.
    """

    limite_tokens: int = Field(gt=0)


def _enmascarar(api_key: str) -> str:
    """Nunca se devuelve la key completa — ni al conectar ni al consultar el
    estado. Los últimos 4 caracteres alcanzan para reconocerla sin exponerla.
    """
    return f"···{api_key[-4:]}" if len(api_key) > 4 else "···"


def _uso_dict(uso: UsoAnthropic) -> dict[str, Any]:
    return {
        "limite_tokens": uso.limite_tokens,
        "tokens_usados": uso.tokens_usados,
        "porcentaje": round(uso.porcentaje(), 2),
    }


async def _uso_actual(sesion: AsyncSession) -> dict[str, Any] | None:
    registro = await RepositorioUsoAnthropicSQLAlchemy(sesion).obtener()
    if registro is None or registro.limite_tokens <= 0:
        return None
    return _uso_dict(registro)


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
        "uso": await _uso_actual(sesion),
    }


@router.get("/estado")
async def estado(sesion: AsyncSession = Depends(obtener_sesion)) -> dict[str, Any]:
    credencial = await RepositorioCredencialAnthropicSQLAlchemy(sesion).obtener()
    if credencial is None:
        return {"conectado": False, "modelo": config.anthropic_model, "uso": None}

    return {
        "conectado": True,
        "modelo": config.anthropic_model,
        "clave": _enmascarar(credencial.api_key),
        "uso": await _uso_actual(sesion),
    }


@router.get("/uso")
async def uso(sesion: AsyncSession = Depends(obtener_sesion)) -> dict[str, Any] | None:
    return await _uso_actual(sesion)


@router.put("/uso")
async def establecer_uso(
    datos: LimiteUsoCrear, sesion: AsyncSession = Depends(obtener_sesion)
) -> dict[str, Any]:
    registro = await RepositorioUsoAnthropicSQLAlchemy(sesion).establecer_limite(
        datos.limite_tokens
    )
    return _uso_dict(registro)


@router.delete("/conexion", status_code=204)
async def desconectar(sesion: AsyncSession = Depends(obtener_sesion)) -> None:
    await RepositorioCredencialAnthropicSQLAlchemy(sesion).eliminar()
