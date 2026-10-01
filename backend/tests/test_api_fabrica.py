"""Traducción HTTP ↔ Líder y servicio de salud, con dobles en memoria."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fabrica_falsos import construir_lider
from fastapi import FastAPI

from app.api.fabrica import obtener_lider, obtener_salud, router
from app.dominio.salud import ServicioSaludFabrica
from app.orchestrator.lider import LiderFabrica


@pytest.fixture
async def contexto(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, LiderFabrica]]:
    lider, repo, bitacora, metricas, _ = construir_lider(tmp_path, tablas=["items"])
    salud = ServicioSaludFabrica(repo, metricas, bitacora, 1.0)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[obtener_lider] = lambda: lider
    app.dependency_overrides[obtener_salud] = lambda: salud
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as cliente:
        yield cliente, lider


async def test_crear_consultar_y_medir_un_encargo(
    contexto: tuple[httpx.AsyncClient, LiderFabrica],
) -> None:
    cliente, lider = contexto
    r = await cliente.post(
        "/api/fabrica/encargos", json={"pedido": "Calcular el total de un carrito"}
    )
    assert r.status_code == 202
    encargo_id = r.json()["id"]
    await lider.esperar(encargo_id)

    r = await cliente.get(f"/api/fabrica/encargos/{encargo_id}")
    assert r.status_code == 200
    assert r.json()["estado"] == "terminado"
    assert r.json()["corriendo"] is False

    r = await cliente.get(f"/api/fabrica/encargos/{encargo_id}/metricas")
    cuerpo = r.json()
    assert {m["etapa"] for m in cuerpo["etapas"]} >= {"especificacion", "revision", "despliegue"}
    assert cuerpo["costo_completo"] is True

    r = await cliente.get(f"/api/fabrica/encargos/{encargo_id}/bitacora")
    assert r.json()["integridad"]["integra"] is True
    assert r.json()["registros"][0]["accion"] == "encargo_recibido"

    r = await cliente.get("/api/fabrica/encargos")
    assert [e["id"] for e in r.json()] == [encargo_id]


async def test_responder_pregunta_y_errores(
    contexto: tuple[httpx.AsyncClient, LiderFabrica],
) -> None:
    cliente, lider = contexto
    r = await cliente.post(
        "/api/fabrica/encargos", json={"pedido": "Agregar etiquetas a los items"}
    )
    encargo_id = r.json()["id"]
    await lider.esperar(encargo_id)
    encargo = (await cliente.get(f"/api/fabrica/encargos/{encargo_id}")).json()
    assert encargo["estado"] == "esperando_humano"
    pregunta_id = encargo["preguntas"][0]["id"]

    r = await cliente.post(
        f"/api/fabrica/encargos/{encargo_id}/preguntas/{pregunta_id}",
        json={"respuesta": "Reutilizar la tabla existente"},
    )
    assert r.status_code == 200
    await lider.esperar(encargo_id)

    # Ya respondida → 409; encargo inexistente → 404.
    r = await cliente.post(
        f"/api/fabrica/encargos/{encargo_id}/preguntas/{pregunta_id}", json={"respuesta": "otra"}
    )
    assert r.status_code == 409
    assert (await cliente.get("/api/fabrica/encargos/nope")).status_code == 404
    r = await cliente.post(f"/api/fabrica/encargos/{encargo_id}/especificaciones/S9/aprobar")
    assert r.status_code == 409


async def test_salud(contexto: tuple[httpx.AsyncClient, LiderFabrica]) -> None:
    cliente, lider = contexto
    r = await cliente.post(
        "/api/fabrica/encargos", json={"pedido": "Calcular el total de un carrito"}
    )
    await lider.esperar(r.json()["id"])

    r = await cliente.get("/api/fabrica/salud")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["signos"]["estado_general"] == "ok"
    assert cuerpo["signos"]["especificaciones_aprobadas"] == 1
    assert cuerpo["integridad"]["integra"] is True
    assert len(cuerpo["velocidad"]) == 14
    assert cuerpo["velocidad"][-1]["especificaciones_aprobadas"] == 1


async def test_pedido_vacio_es_422(contexto: tuple[httpx.AsyncClient, LiderFabrica]) -> None:
    cliente, _ = contexto
    assert (await cliente.post("/api/fabrica/encargos", json={"pedido": ""})).status_code == 422


async def test_config_expone_paralelismo_y_orquestador(
    contexto: tuple[httpx.AsyncClient, LiderFabrica],
) -> None:
    cliente, _ = contexto
    cuerpo = (await cliente.get("/api/fabrica/config")).json()
    assert cuerpo["paralelismo"] == 3
    assert cuerpo["orquestador"] == "local"
    assert cuerpo["prefect_ui_url"] is None


async def test_importar_documento_devuelve_el_pedido(
    contexto: tuple[httpx.AsyncClient, LiderFabrica],
) -> None:
    cliente, _ = contexto
    spec = "- Registrar productos con nombre y precio\n- Calcular el total de un carrito\n"
    r = await cliente.post(
        "/api/fabrica/importar",
        files={"archivo": ("pedido.md", spec.encode("utf-8"), "text/markdown")},
    )
    assert r.status_code == 200
    assert r.json() == {"nombre": "pedido.md", "pedido": spec.strip()}

    r = await cliente.post(
        "/api/fabrica/importar",
        files={"archivo": ("foto.png", b"\x89PNG....", "image/png")},
    )
    assert r.status_code == 422
    assert "Formato no soportado" in r.json()["detail"]


async def test_reiniciar_ejecuciones_y_nueva_version(
    contexto: tuple[httpx.AsyncClient, LiderFabrica],
) -> None:
    cliente, lider = contexto
    v1 = (
        await cliente.post(
            "/api/fabrica/encargos", json={"pedido": "Calcular el total de un carrito"}
        )
    ).json()
    await lider.esperar(v1["id"])

    r = await cliente.post("/api/fabrica/linea/reiniciar")
    assert r.json()["archivados"] == [v1["id"]]
    assert (await cliente.get("/api/fabrica/encargos")).json() == []  # la línea quedó limpia
    todos = (await cliente.get("/api/fabrica/encargos", params={"incluir_archivados": True})).json()
    assert [e["id"] for e in todos] == [v1["id"]]

    [ejecucion] = (await cliente.get("/api/fabrica/ejecuciones")).json()
    assert ejecucion["id"] == v1["id"] and ejecucion["carpeta"] and ejecucion["archivado_en"]
    archivos = (await cliente.get(f"/api/fabrica/ejecuciones/{v1['id']}/archivos")).json()
    ruta = next(
        a["ruta"]
        for a in archivos
        if a["ruta"].startswith("src/") and a["ruta"] != "src/__init__.py"
    )
    r = await cliente.get(f"/api/fabrica/ejecuciones/{v1['id']}/archivo", params={"ruta": ruta})
    assert "def " in r.json()["contenido"]
    r = await cliente.get(f"/api/fabrica/ejecuciones/{v1['id']}/archivo", params={"ruta": "../x"})
    assert r.status_code == 409

    r = await cliente.post(
        "/api/fabrica/encargos",
        json={"pedido": "Aplicar un cupón de descuento", "base_id": v1["id"]},
    )
    v2 = r.json()
    assert (v2["version"], v2["padre_id"], v2["linaje"]) == (2, v1["id"], v1["id"])
    await lider.esperar(v2["id"])
    assert [e["id"] for e in (await cliente.get("/api/fabrica/encargos")).json()] == [v2["id"]]

    r = await cliente.post(
        "/api/fabrica/encargos", json={"pedido": "algo nuevo", "base_id": "nope"}
    )
    assert r.status_code == 404
