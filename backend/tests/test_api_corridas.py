"""POST /api/run acepta un body opcional {caso_de_uso}; GET /api/casos-de-uso
expone la metadata para que el frontend no la hardcodee (BE-05).

No lanzamos una corrida real acá: dispararía BackendAgent/FrontendAgent/
DeployAgent de verdad (asyncio.create_task en segundo plano), que es
justamente lo que test_agentes.py y test_orquestador.py ya prueban de forma
aislada. Acá solo verificamos la traducción HTTP <-> orquestador.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.agents.casos_de_uso import CASOS_DE_USO
from app.api.corridas import router as corridas_router
from app.orchestrator.orquestador import orquestador


@pytest.fixture
async def cliente() -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    app.include_router(corridas_router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_casos_de_uso_expone_los_casos_registrados(cliente: httpx.AsyncClient) -> None:
    r = await cliente.get("/api/casos-de-uso")
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert ids == {c.id for c in CASOS_DE_USO}
    assert "items" in ids and "calculadora" in ids


async def test_run_sin_body_es_valido_el_comportamiento_de_siempre(
    cliente: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Con la corrida "en curso" evitamos que de verdad se dispare el pipeline
    # en segundo plano; alcanza con confirmar que no explota por falta de body.
    monkeypatch.setattr(orquestador, "_corriendo", True)
    r = await cliente.post("/api/run")
    assert r.status_code == 409  # confirma que llegó a validar, no un 422 por body


async def test_run_con_caso_de_uso_desconocido_da_422(
    cliente: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orquestador, "_corriendo", False)
    r = await cliente.post("/api/run", json={"caso_de_uso": "no-existe"})
    assert r.status_code == 422


async def test_run_ya_en_curso_da_409(
    cliente: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orquestador, "_corriendo", True)
    r = await cliente.post("/api/run", json={"caso_de_uso": None})
    assert r.status_code == 409
