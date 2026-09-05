"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

import importlib.util
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adaptadores.persistencia_sqlalchemy import crear_tablas
from .api import corridas_router, items_router
from .api.corridas import registrar_post_corrida
from .config import config
from .websocket import gestor, ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)
log = logging.getLogger("orquesta")


def montar_router_generado(app: FastAPI) -> bool:
    """Monta app/generated/item_routes.py si existe.

    Se llama al arrancar y otra vez al terminar una corrida, para que los
    endpoints que generó el BackendAgent aparezcan sin reiniciar el proceso.
    """
    archivo = Path(config.dir_generado_backend) / "item_routes.py"
    if not archivo.is_file():
        return False
    try:
        spec = importlib.util.spec_from_file_location("app.generated.item_routes", archivo)
        if spec is None or spec.loader is None:
            return False
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        app.include_router(modulo.router)
        # FastAPI cachea el esquema OpenAPI; sin esto /docs no muestra lo nuevo.
        app.openapi_schema = None
        log.info("Router generado montado desde %s", archivo)
        return True
    except Exception:  # noqa: BLE001
        log.exception("No se pudo montar el router generado")
        return False


@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    await crear_tablas()
    await gestor.iniciar_retransmision()
    montar_router_generado(app)
    registrar_post_corrida(lambda: montar_router_generado(app))
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
app.include_router(ws_router)


@app.get("/api/health", tags=["salud"])
async def salud() -> dict:
    return {
        "ok": True,
        "brain": config.brain,
        "deploy_enabled": config.deploy_enabled,
        "conexiones_ws": gestor.n_conexiones,
    }


@app.post("/api/generated/reload", tags=["salud"])
async def recargar_generado() -> dict:
    """Vuelve a montar el router generado sin reiniciar el proceso."""
    montado = montar_router_generado(app)
    return {"montado": montado}
