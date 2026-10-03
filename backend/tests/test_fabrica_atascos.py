"""Garantía de terminación: un encargo no queda girando ni colgado.

Casos reales que lo motivaron: con "Reintentar" sobre el mismo error la
especificación volvía a preguntar para siempre; un cerebro que no respondía
dejaba el encargo "en curso" sin fin; y no había forma de cortar ni de cerrar
un encargo con lo ya aprobado. La detección de atascos sigue la idea del
StuckDetector de OpenHands: mismo error repetido, vaivén entre dos errores o
los mismos archivos otra vez.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fabrica_falsos import EjecutorConSalidas, EjecutorGuionado, construir_lider

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.dominio.fabrica import (
    Consumo,
    PoliticaFabrica,
    RespuestaMedida,
    ResultadoComando,
    detectar_atasco,
    huella_rechazo,
)

PEDIDO = "Calcular el total de un carrito con impuestos"


# --- dominio ---


def test_la_huella_ignora_tiempos_numeros_y_rutas() -> None:
    a = "Pruebas fallaron: 3 failed, 2 passed in 1.62s (C:\\tmp\\x\\test_a.py:12)"
    b = "Pruebas fallaron: 4 failed, 1 passed in 0.31s (C:\\otro\\y\\test_a.py:90)"
    assert huella_rechazo(a) == huella_rechazo(b)
    assert huella_rechazo(a) != huella_rechazo("ImportError: cannot import name total")


def test_detectar_atasco_por_repeticion_vaiven_y_total() -> None:
    assert detectar_atasco(["a", "b"]) is None
    assert detectar_atasco(["a", "a", "a"]) == "el mismo error se repitió 3 veces seguidas"
    assert detectar_atasco(["a", "b", "a", "b"]) == "alterna entre dos errores sin avanzar"
    assert "3 veces en total" in (detectar_atasco(["a", "b", "a", "c", "a"]) or "")
    assert detectar_atasco(["a", "b", "c", "d"]) is None


# --- el Líder ---


async def test_reintentar_el_mismo_error_no_gira_para_siempre(tmp_path: Path) -> None:
    """Reintentar → atasco → reescritura desde cero → sigue igual → se cierra."""
    lider, _, bitacora, _, bus = construir_lider(tmp_path, ejecutor=EjecutorGuionado([1]))
    creado = await lider.crear(PEDIDO)
    await lider.esperar(creado.id)
    [duda] = (await lider.obtener(creado.id)).preguntas_abiertas()

    await lider.responder(creado.id, duda.id, "Reintentar")
    await lider.esperar(creado.id)

    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "fallido"
    assert not encargo.preguntas_abiertas()
    [espec] = encargo.especificaciones
    assert espec.estado == "fallida"
    assert espec.motivo.startswith("Atascada:")
    assert espec.estrategia == "reescritura"
    assert {"atasco", "especificacion_atascada"} <= set(bitacora.acciones())
    assert any("(reescritura)" in e.msg for e in bus.eventos)


async def test_el_tope_de_rondas_cierra_sin_volver_a_preguntar(tmp_path: Path) -> None:
    errores = [(1, f"FAILED - {palabra}") for palabra in ("uno", "dos", "tres", "cuatro")]
    lider, *_ = construir_lider(
        tmp_path,
        ejecutor=EjecutorConSalidas(errores),
        politica=PoliticaFabrica(max_intentos=2, max_rondas=2),
    )
    creado = await lider.crear(PEDIDO)
    await lider.esperar(creado.id)

    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "fallido"
    assert not encargo.preguntas_abiertas()
    assert "tope de 2 intentos" in encargo.especificaciones[0].motivo


class CerebroTerco(CerebroGuionado):
    """Un cerebro "real" que entrega siempre el mismo código, que no pasa."""

    nombre = "terco"

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        texto = respaldo
        if "Implementador" in instruccion:
            archivos = json.loads(respaldo)["archivos"]
            texto = json.dumps(
                {"archivos": [{**a, "contenido": a["contenido"] + "# v\n"} for a in archivos]}
            )
        return RespuestaMedida(texto, Consumo("terco", 1, 1, 0.0))


async def test_los_mismos_archivos_otra_vez_cuentan_como_atasco(tmp_path: Path) -> None:
    errores = [(1, "FAILED - uno"), (1, "FAILED - dos"), (1, "FAILED - tres")]
    lider, _, bitacora, *_ = construir_lider(
        tmp_path,
        cerebro=CerebroTerco(),
        ejecutor=EjecutorConSalidas(errores),
        politica=PoliticaFabrica(aprobacion_humana="nunca"),
    )
    creado = await lider.crear(PEDIDO)
    await lider.esperar(creado.id)

    atascos = [r for r in bitacora.registros if r.accion == "atasco"]
    assert atascos and "mismos archivos" in atascos[0].evidencia["razon"]
    assert (await lider.obtener(creado.id)).estado == "fallido"


class EjecutorColgado:
    async def ejecutar(
        self, directorio: str, comando: list[str], timeout_s: float
    ) -> ResultadoComando:
        await asyncio.sleep(30)
        return ResultadoComando(comando, 0, "", 30, "falso")


async def test_una_etapa_colgada_se_corta_y_el_encargo_termina(tmp_path: Path) -> None:
    lider, _, bitacora, *_ = construir_lider(
        tmp_path, ejecutor=EjecutorColgado(), politica=PoliticaFabrica(timeout_etapa_s=0.3)
    )
    creado = await lider.crear(PEDIDO)
    await asyncio.wait_for(lider.esperar(creado.id), 10)

    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "fallido"
    assert "superó el tope" in encargo.especificaciones[0].motivo
    assert "etapa_vencida" in bitacora.acciones()


async def test_detener_y_cerrar_con_lo_aprobado(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path, ejecutor=EjecutorColgado())
    creado = await lider.crear(PEDIDO)
    for _ in range(100):
        if any(e.estado == "en_curso" for e in (await lider.obtener(creado.id)).especificaciones):
            break
        await asyncio.sleep(0.02)

    detenido = await lider.detener(creado.id)
    assert detenido.estado == "interrumpido"
    assert not lider.corriendo(creado.id)
    assert all(e.estado != "en_curso" for e in detenido.especificaciones)

    cerrado = await lider.finalizar(creado.id)
    assert cerrado.estado == "fallido"
    assert cerrado.motivo == "Cerrado por una persona con 0 de 1 especificaciones aprobadas"
    assert cerrado.especificaciones[0].motivo.startswith("Sin terminar")


async def test_cerrar_contesta_las_preguntas_abiertas(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path, ejecutor=EjecutorGuionado([1]))
    creado = await lider.crear(PEDIDO)
    await lider.esperar(creado.id)
    assert (await lider.obtener(creado.id)).preguntas_abiertas()

    cerrado = await lider.finalizar(creado.id)
    assert not cerrado.preguntas_abiertas()
    assert cerrado.estado == "fallido"


async def test_reanudar_con_una_pregunta_abierta_no_la_duplica(tmp_path: Path) -> None:
    lider, repo, *_ = construir_lider(tmp_path, ejecutor=EjecutorGuionado([1]))
    creado = await lider.crear(PEDIDO)
    await lider.esperar(creado.id)
    # Como queda tras un reinicio del proceso a mitad de la espera.
    encargo = await lider.obtener(creado.id)
    encargo.estado = "interrumpido"
    await repo.guardar(encargo)

    reanudado = await lider.reanudar(creado.id)
    await lider.esperar(creado.id)

    assert reanudado.estado == "esperando_humano"
    assert not lider.corriendo(creado.id)
    assert len((await lider.obtener(creado.id)).preguntas_abiertas()) == 1
