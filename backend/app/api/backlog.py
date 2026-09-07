"""Adaptador de entrada HTTP: lee docs/BACKLOG.md y agrega tareas nuevas."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from ..adaptadores.backlog_markdown import RepositorioBacklogMarkdown
from ..config import config
from ..dominio.modelos import TareaBacklog
from ..dominio.servicios import ServicioBacklog

router = APIRouter(prefix="/api/backlog", tags=["backlog"])


class TareaCrear(BaseModel):
    titulo: str = Field(min_length=1, max_length=140)
    cuerpo: str = Field(min_length=1, max_length=4000)
    lado: Literal["BE", "FE", "DE"]


class TareaLeer(BaseModel):
    id: str
    titulo: str
    cuerpo: str
    lado: Literal["BE", "FE", "DE"]


def _a_leer(tarea: TareaBacklog) -> TareaLeer:
    return TareaLeer(id=tarea.id, titulo=tarea.titulo, cuerpo=tarea.cuerpo, lado=tarea.lado)


def obtener_servicio_backlog() -> ServicioBacklog:
    return ServicioBacklog(RepositorioBacklogMarkdown(Path(config.ruta_backlog)))


@router.get("", response_model=list[TareaLeer])
async def listar(servicio: ServicioBacklog = Depends(obtener_servicio_backlog)) -> list[TareaLeer]:
    return [_a_leer(t) for t in servicio.listar()]


@router.post("", response_model=TareaLeer, status_code=status.HTTP_201_CREATED)
async def agregar(
    datos: TareaCrear, servicio: ServicioBacklog = Depends(obtener_servicio_backlog)
) -> TareaLeer:
    return _a_leer(servicio.agregar(datos.titulo, datos.cuerpo, datos.lado))
