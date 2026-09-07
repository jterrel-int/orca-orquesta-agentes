"""Adaptador de entrada HTTP: lee docs/BACKLOG.md y agrega tareas nuevas."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from ..adaptadores.backlog_markdown import RepositorioBacklogMarkdown
from ..adaptadores.extraccion_documentos import extraer_texto
from ..adaptadores.fabricas import construir_cerebro
from ..config import config
from ..dominio.errores import DocumentoNoLegible
from ..dominio.modelos import TareaBacklog
from ..dominio.servicios import ServicioBacklog

router = APIRouter(prefix="/api/backlog", tags=["backlog"])

# 2 MB alcanza de sobra para una especificación de texto; más que eso es casi
# seguro un archivo con contenido que no es texto (o el formato equivocado).
_TAMANO_MAXIMO_BYTES = 2_000_000
_TEXTO_PEGADO_MINIMO = 30


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


async def obtener_servicio_backlog() -> ServicioBacklog:
    repo = RepositorioBacklogMarkdown(Path(config.ruta_backlog))
    return ServicioBacklog(repo, await construir_cerebro())


@router.get("", response_model=list[TareaLeer])
async def listar(servicio: ServicioBacklog = Depends(obtener_servicio_backlog)) -> list[TareaLeer]:
    return [_a_leer(t) for t in servicio.listar()]


@router.post("", response_model=TareaLeer, status_code=status.HTTP_201_CREATED)
async def agregar(
    datos: TareaCrear, servicio: ServicioBacklog = Depends(obtener_servicio_backlog)
) -> TareaLeer:
    return _a_leer(servicio.agregar(datos.titulo, datos.cuerpo, datos.lado))


@router.post("/generar", response_model=list[TareaLeer], status_code=status.HTTP_201_CREATED)
async def generar_desde_especificacion(
    alcance: Literal["BE", "FE", "todo"] = Form(...),
    archivo: UploadFile | None = File(None),
    texto: str | None = Form(None),
    servicio: ServicioBacklog = Depends(obtener_servicio_backlog),
) -> list[TareaLeer]:
    """Convierte una especificación (documento subido o texto pegado) en
    varias tareas nuevas de docs/BACKLOG.md.
    """
    if archivo is None and not (texto or "").strip():
        raise HTTPException(
            status_code=422, detail="Subí un documento o pegá el texto de la especificación."
        )

    if archivo is not None:
        contenido = await archivo.read()
        if len(contenido) > _TAMANO_MAXIMO_BYTES:
            raise HTTPException(status_code=413, detail="El documento supera los 2 MB.")
        try:
            texto_final = extraer_texto(archivo.filename or "", contenido)
        except DocumentoNoLegible as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    else:
        texto_final = (texto or "").strip()
        if len(texto_final) < _TEXTO_PEGADO_MINIMO:
            raise HTTPException(status_code=422, detail="El texto pegado es demasiado corto.")

    tareas = await servicio.generar_desde_especificacion(texto_final, alcance)
    return [_a_leer(t) for t in tareas]
