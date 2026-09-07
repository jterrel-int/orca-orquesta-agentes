"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adaptadores.fabricas import estado_cerebro
from .adaptadores.persistencia_sqlalchemy import crear_tablas
from .agents.casos_de_uso import archivos_backend_generados
from .api import (
    anthropic_router,
    backlog_router,
    corridas_router,
    items_router,
    render_router,
    vercel_router,
)
from .api.corridas import registrar_post_corrida
from .config import config
from .websocket import gestor, ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)
log = logging.getLogger("orquesta")


def montar_router_generado(app: FastAPI) -> bool:
    """Monta los routers generados en app/generated/ que existan en disco.

    Cada caso de uso (ver agents/casos_de_uso.py) tiene su propio archivo y su
    propio prefijo de rutas, así que pueden convivir montados a la vez sin
    colisionar. Se llama al arrancar y otra vez al terminar cada corrida, para
    que los endpoints que acaba de generar el BackendAgent aparezcan sin
    reiniciar el proceso.
    """
    destino = Path(config.dir_generado_backend)
    montado_alguno = False
    for nombre_archivo in archivos_backend_generados():
        archivo = destino / nombre_archivo
        if not archivo.is_file():
            continue
        try:
            modulo_id = Path(nombre_archivo).stem
            spec = importlib.util.spec_from_file_location(f"app.generated.{modulo_id}", archivo)
            if spec is None or spec.loader is None:
                continue
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            app.include_router(modulo.router)
            montado_alguno = True
            log.info("Router generado montado desde %s", archivo)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo montar el router generado (%s)", archivo)

    if montado_alguno:
        # FastAPI cachea el esquema OpenAPI; sin esto /docs no muestra lo nuevo.
        app.openapi_schema = None
    return montado_alguno


async def _post_corrida(app: FastAPI) -> None:
    """Gancho posterior a cada corrida: monta lo nuevo y crea sus tablas."""
    if montar_router_generado(app):
        await crear_tablas()


@asynccontextmanager
async def ciclo_vida(app: FastAPI) -> AsyncIterator[None]:
    # Montar primero: los routers de calculadora/leads/encuesta definen sus
    # propias tablas ORM sobre la Base compartida al importarse, y crear_tablas
    # necesita verlas ya registradas para crearlas.
    montar_router_generado(app)
    await crear_tablas()
    await gestor.iniciar_retransmision()
    registrar_post_corrida(lambda: _post_corrida(app))
    log.info("Orquesta lista · brain=%s · deploy=%s", config.brain, config.deploy_enabled)
    yield
    await gestor.detener_retransmision()


app = FastAPI(
    title="Orquesta",
    description="MVP multiagente: genera, ejecuta y despliega, con telemetría en vivo.",
    version="0.1.0",
    lifespan=ciclo_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.lista_origenes,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items_router)
app.include_router(corridas_router)
app.include_router(backlog_router)
app.include_router(vercel_router)
app.include_router(render_router)
app.include_router(anthropic_router)
app.include_router(ws_router)


@app.get("/api/health", tags=["salud"])
async def salud() -> dict[str, Any]:
    cerebro = await estado_cerebro()
    return {
        "ok": True,
        "brain": config.brain,
        "cerebro_activo": cerebro["activo"],
        "cerebro_modelo": cerebro["modelo"],
        "cerebro_fuente": cerebro["fuente"],
        "deploy_enabled": config.deploy_enabled,
        "conexiones_ws": gestor.n_conexiones,
        "advertencias": config.advertencias(),
        "vercel_token_configurado": config.vercel_token is not None,
        "origenes_permitidos": config.lista_origenes,
    }


@app.post("/api/generated/reload", tags=["salud"])
async def recargar_generado() -> dict[str, Any]:
    """Vuelve a montar los routers generados sin reiniciar el proceso."""
    montado = montar_router_generado(app)
    if montado:
        await crear_tablas()
    return {"montado": montado}
