"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adaptadores.fabricas import construir_lider_fabrica, estado_cerebro
from .adaptadores.persistencia_sqlalchemy import crear_tablas
from .api import anthropic_router, fabrica_router, render_router, vercel_router
from .config import config
from .websocket import gestor, ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)
log = logging.getLogger("orquesta")


@asynccontextmanager
async def ciclo_vida(app: FastAPI) -> AsyncIterator[None]:
    await crear_tablas()
    interrumpidos = await construir_lider_fabrica().recuperar_interrumpidos()
    if interrumpidos:
        log.warning("Encargos de la fábrica interrumpidos por el reinicio: %s", interrumpidos)
    await gestor.iniciar_retransmision()
    log.info("Orquesta lista · brain=%s · deploy=%s", config.brain, config.deploy_enabled)
    yield
    await gestor.detener_retransmision()


app = FastAPI(
    title="Orquesta",
    description="Fábrica de software agéntica: del pedido a la especificación, el código "
    "probado y el despliegue, con telemetría en vivo.",
    version="0.2.0",
    lifespan=ciclo_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.lista_origenes,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fabrica_router)
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
        "cerebro_cuenta": cerebro["cuenta"],
        "deploy_enabled": config.deploy_enabled,
        "conexiones_ws": gestor.n_conexiones,
        "advertencias": config.advertencias(),
        "vercel_token_configurado": config.vercel_token is not None,
        "origenes_permitidos": config.lista_origenes,
    }
