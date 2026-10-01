"""Fábrica de software: encargos, decisiones humanas, bitácora y salud.

Adaptador de entrada: traduce HTTP a llamadas al Líder y al servicio de
salud. El progreso en vivo viaja por /ws con run_id = id del encargo.
"""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from ..adaptadores import persistencia_sqlalchemy as persistencia
from ..adaptadores.cache_llm import estado_cache, limpiar_cache
from ..adaptadores.extraccion_documentos import extraer_texto
from ..adaptadores.fabricas import construir_lider_fabrica, construir_servicio_salud_fabrica
from ..config import config
from ..dominio.errores import AccionNoPermitida, DocumentoNoLegible, EncargoNoEncontrado
from ..dominio.fabrica import Encargo
from ..dominio.salud import ServicioSaludFabrica
from ..orchestrator.lider import LiderFabrica

router = APIRouter(prefix="/api/fabrica", tags=["fábrica"])


def obtener_lider() -> LiderFabrica:
    return construir_lider_fabrica()


def obtener_salud() -> ServicioSaludFabrica:
    return construir_servicio_salud_fabrica()


class NuevoEncargo(BaseModel):
    pedido: str = Field(min_length=3, max_length=8000)
    # Para iterar: la versión de la que parte (copia sus archivos).
    base_id: str | None = Field(default=None, max_length=64)


class Respuesta(BaseModel):
    respuesta: str = Field(min_length=1, max_length=2000)


def _vista(encargo: Encargo, lider: LiderFabrica) -> dict[str, Any]:
    datos = encargo.a_dict()
    datos["corriendo"] = lider.corriendo(encargo.id)
    datos["linaje"] = encargo.linaje
    return datos


async def _con_errores(accion: Any) -> Any:
    try:
        return await accion
    except EncargoNoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except AccionNoPermitida as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/encargos", status_code=status.HTTP_202_ACCEPTED)
async def crear_encargo(
    entrada: NuevoEncargo, lider: LiderFabrica = Depends(obtener_lider)
) -> dict[str, Any]:
    """Arranca el pipeline en segundo plano y responde de inmediato. Con
    `base_id` es una nueva versión de ese encargo.
    """
    return _vista(await _con_errores(lider.crear(entrada.pedido, base_id=entrada.base_id)), lider)


@router.get("/encargos")
async def listar_encargos(
    incluir_archivados: bool = False,
    salud: ServicioSaludFabrica = Depends(obtener_salud),
    lider: LiderFabrica = Depends(obtener_lider),
) -> list[dict[str, Any]]:
    """Los de la línea actual; los archivados (por un reinicio) solo si se piden."""
    return [
        _vista(e, lider)
        for e in await salud.encargos()
        if incluir_archivados or e.archivado_en is None
    ]


@router.get("/encargos/{encargo_id}")
async def obtener_encargo(
    encargo_id: str, lider: LiderFabrica = Depends(obtener_lider)
) -> dict[str, Any]:
    return _vista(await _con_errores(lider.obtener(encargo_id)), lider)


@router.post("/encargos/{encargo_id}/preguntas/{pregunta_id}")
async def responder_pregunta(
    encargo_id: str,
    pregunta_id: str,
    entrada: Respuesta,
    lider: LiderFabrica = Depends(obtener_lider),
) -> dict[str, Any]:
    encargo = await _con_errores(lider.responder(encargo_id, pregunta_id, entrada.respuesta))
    return _vista(encargo, lider)


@router.post("/encargos/{encargo_id}/especificaciones/{espec_id}/aprobar")
async def aprobar_especificacion(
    encargo_id: str, espec_id: str, lider: LiderFabrica = Depends(obtener_lider)
) -> dict[str, Any]:
    encargo = await _con_errores(lider.decidir(encargo_id, espec_id, aprobar=True))
    return _vista(encargo, lider)


@router.post("/encargos/{encargo_id}/especificaciones/{espec_id}/rechazar")
async def rechazar_especificacion(
    encargo_id: str, espec_id: str, lider: LiderFabrica = Depends(obtener_lider)
) -> dict[str, Any]:
    encargo = await _con_errores(lider.decidir(encargo_id, espec_id, aprobar=False))
    return _vista(encargo, lider)


@router.post("/encargos/{encargo_id}/reanudar")
async def reanudar_encargo(
    encargo_id: str, lider: LiderFabrica = Depends(obtener_lider)
) -> dict[str, Any]:
    return _vista(await _con_errores(lider.reanudar(encargo_id)), lider)


@router.get("/encargos/{encargo_id}/bitacora")
async def bitacora_encargo(
    encargo_id: str, salud: ServicioSaludFabrica = Depends(obtener_salud)
) -> dict[str, Any]:
    """Los registros del encargo más la verificación de la cadena completa:
    un registro de este encargo puede estar intacto y aun así haber sido
    alterado uno anterior de otro encargo.
    """
    integridad = await salud.integridad()
    return {
        "integridad": asdict(integridad),
        "registros": [asdict(r) for r in await salud.bitacora(encargo_id)],
    }


@router.get("/encargos/{encargo_id}/metricas")
async def metricas_encargo(
    encargo_id: str, salud: ServicioSaludFabrica = Depends(obtener_salud)
) -> dict[str, Any]:
    metricas = await salud.metricas(encargo_id)
    costos = [m.costo_usd for m in metricas]
    return {
        "etapas": [asdict(m) for m in metricas],
        "costo_total_usd": round(sum(c or 0.0 for c in costos), 6),
        "costo_completo": all(c is not None for c in costos),
        "duracion_total_s": round(sum(m.duracion_s for m in metricas), 2),
        "tokens_total": sum(m.tokens_entrada + m.tokens_salida for m in metricas),
    }


@router.get("/salud")
async def salud_fabrica(salud: ServicioSaludFabrica = Depends(obtener_salud)) -> dict[str, Any]:
    ahora = datetime.now(UTC)
    return {
        "signos": asdict(await salud.signos_vitales(ahora)),
        "velocidad": [asdict(p) for p in await salud.velocidad(ahora)],
        "integridad": asdict(await salud.integridad()),
    }


@router.get("/cache")
async def estado_cache_llm() -> dict[str, Any]:
    """Aciertos y ahorro estimado de la caché de respuestas. El ahorro es
    informativo: nunca se resta del gasto real de los encargos.
    """
    return {"activa": config.fabrica_cache_llm, **await estado_cache(persistencia.FabricaSesion)}


@router.post("/cache/limpiar")
async def limpiar_cache_llm() -> dict[str, int]:
    return {"borradas": await limpiar_cache(persistencia.FabricaSesion)}


@router.get("/plugins")
async def plugins_cargados(lider: LiderFabrica = Depends(obtener_lider)) -> dict[str, list[str]]:
    return {"cargados": lider.plugins.cargados, "errores": lider.plugins.errores}


@router.get("/config")
async def configuracion_fabrica(lider: LiderFabrica = Depends(obtener_lider)) -> dict[str, Any]:
    """Lo que el panel necesita saber para mostrar cómo corre la fábrica."""
    return {
        "paralelismo": lider.paralelismo,
        "orquestador": "prefect" if lider.usa_prefect else "local",
        "prefect_ui_url": config.prefect_ui_url if lider.usa_prefect else None,
        "aprobacion_humana": lider.politica.aprobacion_humana,
        "max_intentos": lider.politica.max_intentos,
        "presupuesto_usd": lider.politica.presupuesto_encargo_usd,
        "cache_llm": config.fabrica_cache_llm,
    }


_MAX_DOCUMENTO_BYTES = 5 * 1024 * 1024


@router.post("/importar")
async def importar_documento(archivo: UploadFile = File(...)) -> dict[str, str]:
    """Extrae el texto de una especificación (.txt, .md, .pdf, .docx) para
    usarlo como pedido. No crea el encargo: la persona revisa el texto en el
    panel y recién ahí encarga, así un PDF mal leído no dispara agentes.
    """
    contenido = await archivo.read(_MAX_DOCUMENTO_BYTES + 1)
    if len(contenido) > _MAX_DOCUMENTO_BYTES:
        raise HTTPException(status_code=413, detail="El documento supera los 5 MB")
    try:
        texto = extraer_texto(archivo.filename or "", contenido)
    except DocumentoNoLegible as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # El pedido del encargo admite hasta 8000 caracteres (NuevoEncargo).
    return {"nombre": archivo.filename or "", "pedido": texto[:8000]}


@router.post("/linea/reiniciar")
async def reiniciar_linea(lider: LiderFabrica = Depends(obtener_lider)) -> dict[str, list[str]]:
    """Detiene lo que corre y archiva los encargos actuales. No borra nada:
    siguen en Ejecuciones, con su bitácora y sus archivos.
    """
    return await lider.reiniciar_linea()


@router.get("/ejecuciones")
async def listar_ejecuciones(lider: LiderFabrica = Depends(obtener_lider)) -> list[dict[str, Any]]:
    """Cada carpeta de fabrica_espacios/ cruzada con su encargo."""
    return [{**asdict(e), "corriendo": lider.corriendo(e.id)} for e in await lider.ejecuciones()]


@router.get("/ejecuciones/{encargo_id}/archivos")
async def archivos_ejecucion(
    encargo_id: str, lider: LiderFabrica = Depends(obtener_lider)
) -> list[dict[str, object]]:
    archivos: list[dict[str, object]] = await _con_errores(lider.archivos(encargo_id))
    return archivos


@router.get("/ejecuciones/{encargo_id}/archivo")
async def leer_archivo_ejecucion(
    encargo_id: str, ruta: str, lider: LiderFabrica = Depends(obtener_lider)
) -> dict[str, str]:
    """Solo lectura, y solo dentro de la carpeta de esa ejecución."""
    contenido = await _con_errores(lider.leer_archivo(encargo_id, ruta))
    return {"ruta": ruta, "contenido": contenido}
