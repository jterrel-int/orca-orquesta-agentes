"""POST /api/backlog/generar: sube o pega una especificación y devuelve las
tareas que quedaron agregadas a docs/BACKLOG.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.api import backlog as api_backlog
from app.dominio.servicios import ServicioBacklog


@pytest.fixture
async def cliente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    ruta = tmp_path / "BACKLOG.md"
    monkeypatch.setattr(api_backlog.config, "ruta_backlog", str(ruta))

    app = FastAPI()
    app.include_router(api_backlog.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


ESPECIFICACION = (
    "# Alta de productos\n\nHace falta un endpoint que guarde productos en la base de datos.\n\n"
    "# Pantalla de catálogo\n\nUn componente con una grilla de tarjetas y un formulario.\n"
)


async def test_generar_sin_archivo_ni_texto_da_422(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/backlog/generar", data={"alcance": "todo"})
    assert r.status_code == 422


async def test_generar_con_texto_muy_corto_da_422(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/backlog/generar", data={"alcance": "BE", "texto": "muy corto"})
    assert r.status_code == 422


async def test_generar_con_texto_pegado_crea_tareas(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/backlog/generar", data={"alcance": "BE", "texto": ESPECIFICACION})
    assert r.status_code == 201
    tareas = r.json()
    assert len(tareas) == 2
    assert all(t["lado"] == "BE" for t in tareas)
    assert [t["id"] for t in tareas] == ["BE-01", "BE-02"]

    # Quedaron escritas de verdad en docs/BACKLOG.md.
    r2 = await cliente.get("/api/backlog")
    assert len(r2.json()) == 2


async def test_generar_con_archivo_formato_no_soportado_da_422(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post(
        "/api/backlog/generar",
        data={"alcance": "FE"},
        files={"archivo": ("spec.png", b"contenido binario cualquiera", "image/png")},
    )
    assert r.status_code == 422


async def test_generar_con_archivo_txt_valido_crea_tareas(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post(
        "/api/backlog/generar",
        data={"alcance": "todo"},
        files={"archivo": ("spec.txt", ESPECIFICACION.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 201
    tareas = r.json()
    lados = {t["lado"] for t in tareas}
    assert lados <= {"BE", "FE"}


async def test_generar_con_archivo_demasiado_grande_da_413(cliente: httpx.AsyncClient) -> None:
    contenido = b"a" * (2_000_001)
    r = await cliente.post(
        "/api/backlog/generar",
        data={"alcance": "BE"},
        files={"archivo": ("spec.txt", contenido, "text/plain")},
    )
    assert r.status_code == 413


async def test_obtener_servicio_backlog_inyecta_un_cerebro() -> None:
    """No es None: sin esto, generar_desde_especificacion nunca usaría un
    cerebro real aunque hubiera una API key configurada.
    """
    servicio = await api_backlog.obtener_servicio_backlog()
    assert isinstance(servicio, ServicioBacklog)
    assert servicio._cerebro is not None
