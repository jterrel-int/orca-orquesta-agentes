"""Paralelismo real dentro de un encargo, e integración opcional con Prefect."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from fabrica_falsos import construir_lider

from app.dominio.fabrica import Especificacion, niveles
from app.orchestrator import prefect_opcional

TRES = (
    "Registrar productos con nombre y precio. "
    "Calcular el total de un carrito con impuestos. "
    "Aplicar un cupón de descuento sobre el total."
)


class EjecutorLento:
    """Pytest simulado que tarda y cuenta cuántas corridas se solapan."""

    def __init__(self) -> None:
        self.en_vuelo = 0
        self.maximo = 0

    async def ejecutar(self, directorio: str, comando: list[str], timeout_s: float) -> Any:
        from app.dominio.fabrica import ResultadoComando

        self.en_vuelo += 1
        self.maximo = max(self.maximo, self.en_vuelo)
        await asyncio.sleep(0.15)
        self.en_vuelo -= 1
        return ResultadoComando(comando, 0, "1 passed", 0.15, "falso")


def test_niveles_del_grafo() -> None:
    especs = [
        Especificacion("S1", "", ""),
        Especificacion("S2", "", "", depende_de=["S1"]),
        Especificacion("S3", "", "", depende_de=["S1"]),
        Especificacion("S4", "", "", depende_de=["S2", "S3"]),
    ]
    assert niveles(especs) == {"S1": 1, "S2": 2, "S3": 2, "S4": 3}


async def test_las_independientes_corren_a_la_vez(tmp_path: Path) -> None:
    ejecutor = EjecutorLento()
    lider, _, bitacora, metricas, bus = construir_lider(tmp_path, ejecutor=ejecutor)

    creado = await lider.crear(TRES)
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    assert encargo.estado == "terminado", encargo.motivo
    assert [e.depende_de for e in encargo.especificaciones] == [[], ["S1"], ["S1"]]
    # S2 y S3 se revisaron solapadas en el tiempo, no una detrás de otra.
    assert ejecutor.maximo == 2
    tanda = next(r for r in bitacora.registros if r.accion == "tanda_paralela")
    assert tanda.evidencia["especificaciones"] == ["S2", "S3"]
    assert any("2 especificaciones en paralelo" in e.msg for e in bus.eventos)


async def test_el_tope_de_paralelismo_se_respeta(tmp_path: Path) -> None:
    ejecutor = EjecutorLento()
    lider, *_ = construir_lider(tmp_path, ejecutor=ejecutor)
    lider.paralelismo = 1

    creado = await lider.crear(TRES)
    await lider.esperar(creado.id)
    assert (await lider.obtener(creado.id)).estado == "terminado"
    assert ejecutor.maximo == 1


async def test_una_compuerta_humana_no_frena_a_sus_hermanas(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path, ejecutor=EjecutorLento())
    creado = await lider.crear(
        "Registrar productos con nombre y precio. "
        "Eliminar los productos sin stock de la base. "
        "Calcular el total de un carrito con impuestos."
    )
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    estados = {e.id: e.estado for e in encargo.especificaciones}
    assert encargo.estado == "esperando_humano"
    assert estados == {"S1": "aprobada", "S2": "esperando_aprobacion", "S3": "aprobada"}

    await lider.decidir(creado.id, "S2", aprobar=True)
    await lider.esperar(creado.id)
    assert (await lider.obtener(creado.id)).estado == "terminado"


# --- Prefect ---


def _prefect_falso(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    registro: dict[str, list[str]] = {"flows": [], "tasks": []}

    def flow(**opciones: Any) -> Any:
        def decorar(fn: Any) -> Any:
            async def envuelta() -> Any:
                registro["flows"].append(opciones["flow_run_name"])
                return await fn()

            return envuelta

        return decorar

    def task(**opciones: Any) -> Any:
        assert opciones["cache_policy"] == "sin-cache"

        def decorar(fn: Any) -> Any:
            async def envuelta() -> Any:
                registro["tasks"].append(opciones["name"])
                return await fn()

            return envuelta

        return decorar

    modulo = types.ModuleType("prefect")
    modulo.flow = flow  # type: ignore[attr-defined]
    modulo.task = task  # type: ignore[attr-defined]
    politicas = types.ModuleType("prefect.cache_policies")
    politicas.NO_CACHE = "sin-cache"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "prefect", modulo)
    monkeypatch.setitem(sys.modules, "prefect.cache_policies", politicas)
    return registro


async def test_con_prefect_cada_encargo_es_un_flow_y_cada_etapa_un_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registro = _prefect_falso(monkeypatch)
    lider, *_ = construir_lider(tmp_path)
    lider._usar_prefect = True

    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)

    assert (await lider.obtener(creado.id)).estado == "terminado"
    assert registro["flows"] == [f"encargo-{creado.id}"]
    assert registro["tasks"] == [
        "especificacion",
        "implementacion",
        "revision",
        "verificacion",
        "despliegue",
    ]


async def test_sin_prefect_no_se_importa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "prefect", None)  # un import fallaría

    async def trabajo() -> int:
        return 7

    assert await prefect_opcional.en_flujo(False, "f", "r", trabajo) == 7
    assert await prefect_opcional.en_tarea(False, "t", "r", trabajo) == 7
