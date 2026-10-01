"""Reintentos informados: el Implementador ve el error real, el diagnóstico y
el código del que depende; y al agotar los intentos la fábrica pregunta con la
propuesta del Diagnosticador en vez de rendirse en silencio.

Caso real que lo motivó: S4 falló dos veces con "table facturas_pendientes has
no column named proveedor"; el Diagnosticador dio la solución exacta, pero el
reintento no la veía y el encargo terminó "fallido" sin ofrecer nada.
"""

from __future__ import annotations

import json
from pathlib import Path

from fabrica_falsos import construir_lider

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.agents.fabrica.diagnosticador import diagnostico_determinista
from app.dominio.fabrica import Consumo, RespuestaMedida, ResultadoComando, Veredicto
from app.orchestrator.lider import OPCION_REINTENTAR_PROPUESTA

ERROR_REAL = "E   sqlite3.OperationalError: table facturas has no column named proveedor"


class EjecutorConSalidas:
    """Devuelve (código, salida) en orden; después del último, repite el último."""

    def __init__(self, respuestas: list[tuple[int, str]]) -> None:
        self._respuestas = respuestas
        self.llamadas = 0

    async def ejecutar(
        self, directorio: str, comando: list[str], timeout_s: float
    ) -> ResultadoComando:
        codigo, salida = self._respuestas[min(self.llamadas, len(self._respuestas) - 1)]
        self.llamadas += 1
        return ResultadoComando(comando, codigo, salida, 0.01, "falso")


class CerebroEspia(CerebroGuionado):
    """Guionado que guarda (instrucción, contexto) de cada llamada."""

    def __init__(self) -> None:
        self.llamadas: list[tuple[str, str]] = []

    async def pensar_medido(self, instruccion: str, contexto: str = "", *, respaldo: str = ""):  # type: ignore[no-untyped-def]
        self.llamadas.append((instruccion, contexto))
        return RespuestaMedida(respaldo, Consumo("guionado", 0, 0, 0.0))

    def contextos_implementador(self) -> list[dict]:  # type: ignore[type-arg]
        return [json.loads(c) for i, c in self.llamadas if "Implementador" in i]


def _fallo(n: int) -> tuple[int, str]:
    # Motivos distintos en cada intento: así no se dispara la regla de
    # "el mismo rechazo se repitió" y se llega a agotar los intentos.
    return 1, f"{ERROR_REAL}\nFAILED tests/test_x.py::test_{n}\n{n} failed, 3 passed in 0.{n}s"


async def test_el_reintento_ve_el_error_real_y_el_diagnostico(tmp_path: Path) -> None:
    espia = CerebroEspia()
    lider, *_ = construir_lider(
        tmp_path, cerebro=espia, ejecutor=EjecutorConSalidas([_fallo(1), (0, "ok")])
    )
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)

    assert (await lider.obtener(creado.id)).estado == "terminado"
    primero, segundo = espia.contextos_implementador()
    assert primero["detalle_rechazo_previo"] is None
    detalle = segundo["detalle_rechazo_previo"]
    assert "has no column named proveedor" in detalle["salida_pruebas"]
    assert detalle["diagnostico"]  # la explicación del Diagnosticador viaja al reintento
    assert segundo["intentos_previos"][0]["diagnostico"] == detalle["diagnostico"]


async def test_el_implementador_ve_el_codigo_de_sus_dependencias(tmp_path: Path) -> None:
    espia = CerebroEspia()
    lider, *_ = construir_lider(tmp_path, cerebro=espia)
    creado = await lider.crear(
        "Registrar productos con nombre y precio. Calcular el total de un carrito con impuestos."
    )
    await lider.esperar(creado.id)

    contextos = espia.contextos_implementador()
    s1 = next(c for c in contextos if c["especificacion"]["id"] == "S1")
    s2 = next(c for c in contextos if c["especificacion"]["id"] == "S2")
    assert s1["codigo_de_dependencias"] == {}
    [(ruta, codigo)] = s2["codigo_de_dependencias"].items()
    assert ruta.startswith("src/registrar_productos") and "def ejecutar_" in codigo


async def test_al_agotar_los_intentos_pregunta_con_la_propuesta(tmp_path: Path) -> None:
    lider, *_ = construir_lider(
        tmp_path, ejecutor=EjecutorConSalidas([_fallo(1), _fallo(2), (0, "ok")])
    )
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)

    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "esperando_humano"  # no "fallido" en silencio
    [pregunta] = encargo.preguntas_abiertas()
    assert pregunta.opciones[0] == OPCION_REINTENTAR_PROPUESTA
    assert pregunta.propuesta  # la explicación del Diagnosticador
    assert "no pasó la revisión" in pregunta.texto

    await lider.responder(creado.id, pregunta.id, OPCION_REINTENTAR_PROPUESTA)
    await lider.esperar(creado.id)
    final = await lider.obtener(creado.id)
    assert final.estado == "terminado"
    assert "Aplicar la propuesta del Diagnosticador" in final.especificaciones[0].descripcion
    assert pregunta.propuesta in final.especificaciones[0].descripcion


async def test_reanudar_un_fallido_reintenta_lo_que_fallo(tmp_path: Path) -> None:
    lider, repo, *_ = construir_lider(tmp_path)
    creado = await lider.crear(
        "Registrar productos con nombre y precio. Calcular el total de un carrito con impuestos."
    )
    await lider.esperar(creado.id)

    # Como quedó el encargo del caso real: una especificación fallida y el encargo fallido.
    encargo = await repo.obtener(creado.id)
    assert encargo is not None
    encargo.estado, encargo.motivo = "fallido", "Una o más especificaciones no se aprobaron"
    encargo.especificaciones[1].estado = "fallida"
    encargo.especificaciones[1].intentos = 2
    encargo.especificaciones[1].motivo = "Rechazada tras 2 intento(s): 10 failed"
    await repo.guardar(encargo)

    await lider.reanudar(creado.id)
    await lider.esperar(creado.id)
    final = await lider.obtener(creado.id)
    assert final.estado == "terminado"
    assert final.especificaciones[1].estado == "aprobada"


def test_el_mismo_rechazo_con_otro_tiempo_cuenta_como_repetido() -> None:
    anterior = "Pruebas unitarias fallaron (código 1): 10 failed, 17 passed in 1.58s"
    actual = Veredicto(
        False, "Pruebas unitarias fallaron (código 1): 10 failed, 17 passed in 1.62s"
    )
    diagnostico = diagnostico_determinista(actual, [anterior])
    assert diagnostico is not None and diagnostico.causa == "especificacion"
