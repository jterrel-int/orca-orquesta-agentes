"""El Líder de la fábrica de punta a punta, con el cerebro guionado.

El caso feliz usa el EjecutorLocal real: pytest corre de verdad sobre el
código que escribió el Implementador. Los casos de rechazo usan un ejecutor
guionado para forzar cada rama del Diagnosticador.
"""

from __future__ import annotations

from pathlib import Path

from fabrica_falsos import CerebroCaro, EjecutorConSalidas, EjecutorGuionado, construir_lider

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.dominio.fabrica import (
    Consumo,
    PoliticaFabrica,
    Pregunta,
    RespuestaMedida,
    primer_registro_roto,
)

PEDIDO = (
    "Calcular el total de un carrito con impuestos. "
    "Aplicar un cupón de descuento sobre el total calculado."
)


async def test_encargo_completo_de_punta_a_punta(tmp_path: Path) -> None:
    lider, repo, bitacora, metricas, bus = construir_lider(tmp_path)

    creado = await lider.crear(PEDIDO)
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    assert encargo.estado == "terminado", encargo.motivo
    assert [e.id for e in encargo.especificaciones] == ["S1", "S2"]
    assert encargo.especificaciones[1].depende_de == ["S1"]
    assert all(e.estado == "aprobada" and e.intentos == 1 for e in encargo.especificaciones)

    espacio = lider.espacio(creado.id)
    for e in encargo.especificaciones:
        for archivo in e.archivos:
            assert (espacio / archivo).is_file(), archivo
    assert (espacio / ".github" / "workflows" / "ci.yml").is_file()

    # La bitácora es una cadena íntegra y registra lo que realmente pasó.
    assert primer_registro_roto(bitacora.registros) is None
    acciones = bitacora.acciones()
    assert acciones[0] == "encargo_recibido"
    assert acciones.count("archivos_escritos") == 2
    assert acciones[-1] == "encargo_terminado"
    revision = next(r for r in bitacora.registros if r.accion == "revision")
    assert revision.evidencia["evidencia"]["codigo_salida"] == 0
    assert "passed" in revision.evidencia["evidencia"]["salida"]

    # Una métrica por etapa, con tiempo y costo.
    etapas = [m.etapa for m in metricas.metricas]
    assert etapas.count("implementacion") == 2
    assert etapas.count("revision") == 2
    assert etapas.count("verificacion") == 2
    assert etapas[0] == "especificacion" and etapas[-1] == "despliegue"
    assert all(m.duracion_s >= 0 for m in metricas.metricas)

    # Contrato congelado del WebSocket: run_id es el encargo.
    assert {e.run_id for e in bus.eventos} == {creado.id}
    assert {"lider", "especificador", "implementador", "revisor", "verificador"} <= {
        e.agent for e in bus.eventos
    }


async def test_tabla_legada_pausa_y_la_respuesta_se_incorpora(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path, tablas=["items", "leads"])

    creado = await lider.crear("Agregar etiquetas a los items del inventario con un color")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "esperando_humano"
    assert encargo.especificaciones == []
    [pregunta] = encargo.preguntas_abiertas()
    assert "items" in pregunta.texto
    assert pregunta.opciones[0] == "Reutilizar la tabla existente"

    await lider.responder(creado.id, pregunta.id, "Extenderla con columnas nuevas")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "terminado", encargo.motivo
    assert "Extenderla con columnas nuevas" in encargo.especificaciones[0].descripcion


async def test_especificacion_riesgosa_espera_aprobacion_humana(tmp_path: Path) -> None:
    lider, _, bitacora, *_ = construir_lider(tmp_path)

    creado = await lider.crear("Eliminar los clientes inactivos de la base de datos")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "esperando_humano"
    assert encargo.especificaciones[0].estado == "esperando_aprobacion"

    await lider.decidir(creado.id, "S1", aprobar=True)
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "terminado", encargo.motivo
    assert "aprobacion" in bitacora.acciones()


async def test_rechazo_de_implementacion_se_reintenta(tmp_path: Path) -> None:
    ejecutor = EjecutorGuionado([1, 0])
    lider, _, bitacora, metricas, _ = construir_lider(tmp_path, ejecutor=ejecutor)

    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    assert encargo.estado == "terminado", encargo.motivo
    assert encargo.especificaciones[0].intentos == 2
    diagnosticos = [m for m in metricas.metricas if m.etapa == "diagnostico"]
    assert [d.resultado for d in diagnosticos] == ["implementacion"]
    assert bitacora.acciones().count("diagnostico") == 1


async def test_falla_del_harness_bloquea_sin_reintentar(tmp_path: Path) -> None:
    ejecutor = EjecutorGuionado([127], salida="No se encontró el ejecutable: python")
    lider, *_ = construir_lider(tmp_path, ejecutor=ejecutor)

    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    assert encargo.estado == "fallido"
    espec = encargo.especificaciones[0]
    assert espec.estado == "bloqueada"
    assert espec.intentos == 1
    assert "entorno" in espec.motivo
    assert ejecutor.llamadas == 1


async def test_mismo_rechazo_repetido_se_atribuye_a_la_especificacion(tmp_path: Path) -> None:
    lider, *_ = construir_lider(
        tmp_path, ejecutor=EjecutorGuionado([1]), politica=PoliticaFabrica(max_intentos=3)
    )

    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "esperando_humano"
    [pregunta] = encargo.preguntas_abiertas()
    assert pregunta.origen == "diagnosticador" and pregunta.espec_id == "S1"

    await lider.responder(creado.id, pregunta.id, "Descartar")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)
    assert encargo.estado == "fallido"
    assert encargo.especificaciones[0].motivo == "Descartada por decisión humana"


async def test_presupuesto_agotado_detiene_el_encargo(tmp_path: Path) -> None:
    lider, *_ = construir_lider(
        tmp_path, cerebro=CerebroCaro(), politica=PoliticaFabrica(presupuesto_encargo_usd=0.5)
    )

    creado = await lider.crear(PEDIDO)
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    assert encargo.estado == "fallido"
    assert "Presupuesto" in encargo.motivo
    assert encargo.costo_usd >= 0.5


async def test_modo_nunca_no_frena_por_la_tabla_legada(tmp_path: Path) -> None:
    lider, _, bitacora, *_ = construir_lider(
        tmp_path, tablas=["items"], politica=PoliticaFabrica(aprobacion_humana="nunca")
    )

    creado = await lider.crear("Agregar etiquetas a los items del inventario con un color")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    assert encargo.estado == "terminado", encargo.motivo
    especificacion = next(r for r in bitacora.registros if r.accion == "especificaciones")
    assert especificacion.evidencia["decisiones_automaticas"]


async def test_reinicio_deja_interrumpido_y_se_puede_reanudar(tmp_path: Path) -> None:
    lider, repo, *_ = construir_lider(tmp_path)
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)

    # Simula un proceso que murió a mitad de camino.
    encargo = await repo.obtener(creado.id)
    assert encargo is not None
    encargo.estado = "en_curso"
    encargo.especificaciones[0].estado = "en_curso"
    encargo.especificaciones[0].intentos = 0
    await repo.guardar(encargo)

    assert await lider.recuperar_interrumpidos() == [creado.id]
    assert (await lider.obtener(creado.id)).estado == "interrumpido"

    await lider.reanudar(creado.id)
    await lider.esperar(creado.id)
    assert (await lider.obtener(creado.id)).estado == "terminado"


async def test_se_puede_responder_la_segunda_duda_despues_de_reintentar(tmp_path: Path) -> None:
    """Regresión: al elegir "Reintentar" los intentos vuelven a cero, y la duda
    siguiente del Diagnosticador salía con el mismo id que la anterior
    (D-S1-2). Responderla chocaba con la ya respondida: "Esa pregunta no
    existe o ya fue respondida".

    Dos errores distintos (cada uno repetido dos veces) para que la duda
    vuelva a aparecer sin que se dispare la detección de atascos.
    """
    error_a = (1, "FAILED tests/x.py - ImportError: cannot import name carrito")
    error_b = (1, "FAILED tests/x.py - AssertionError: total sin impuestos")
    lider, *_ = construir_lider(
        tmp_path, ejecutor=EjecutorConSalidas([error_a, error_a, error_b, error_b])
    )

    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)
    [primera] = (await lider.obtener(creado.id)).preguntas_abiertas()
    await lider.responder(creado.id, primera.id, "Reintentar")
    await lider.esperar(creado.id)

    encargo = await lider.obtener(creado.id)
    [segunda] = encargo.preguntas_abiertas()
    assert segunda.id != primera.id
    assert len({p.id for p in encargo.preguntas}) == len(encargo.preguntas)

    await lider.responder(creado.id, segunda.id, "Descartar")
    await lider.esperar(creado.id)
    assert (await lider.obtener(creado.id)).estado == "fallido"


async def test_responde_la_abierta_si_un_encargo_viejo_repite_el_id(tmp_path: Path) -> None:
    """Encargos guardados antes del arreglo ya tienen dos dudas con el mismo
    id (una respondida). Responder debe tomar la abierta, sin migrar nada.
    """
    lider, repo, *_ = construir_lider(tmp_path, ejecutor=EjecutorGuionado([1]))
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)

    encargo = await repo.obtener(creado.id)
    assert encargo is not None
    abierta = encargo.preguntas_abiertas()[0]
    vieja = Pregunta(
        abierta.id,
        "duda anterior",
        ["Reintentar"],
        "Reintentar",
        "diagnosticador",
        abierta.espec_id,
    )
    encargo.preguntas.insert(0, vieja)  # la respondida primero, como quedó guardado
    await repo.guardar(encargo)

    await lider.responder(creado.id, abierta.id, "Descartar")
    await lider.esperar(creado.id)
    final = await lider.obtener(creado.id)
    assert final.preguntas_abiertas() == []
    assert final.especificaciones[0].motivo == "Descartada por decisión humana"


class CerebroQueNoResponde(CerebroGuionado):
    """Como claude-cli cuando se le acaba el tiempo: devuelve el respaldo."""

    async def pensar_medido(self, instruccion: str, contexto: str = "", *, respaldo: str = ""):  # type: ignore[no-untyped-def]
        return RespuestaMedida(respaldo, Consumo("claude-cli"))


async def test_si_el_cerebro_no_responde_se_pregunta_sin_revisar_la_plantilla(
    tmp_path: Path,
) -> None:
    """Regresión: la plantilla de respaldo se mandaba a revisar como si fuera
    el trabajo del cerebro; el rechazo se repetía y el Diagnosticador culpaba a
    la especificación. Ahora es "harness" y se pregunta enseguida.
    """
    lider, _, bitacora, metricas, _ = construir_lider(tmp_path, cerebro=CerebroQueNoResponde())
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)

    encargo = await lider.obtener(creado.id)
    [pregunta] = encargo.preguntas_abiertas()
    assert encargo.estado == "esperando_humano"
    assert "no se pudo construir" in pregunta.texto and "CLAUDE_CLI_TIMEOUT_S" in pregunta.texto
    assert "revision" not in bitacora.acciones()  # la plantilla no se revisó
    diagnostico = next(r for r in bitacora.registros if r.accion == "diagnostico")
    assert diagnostico.evidencia["causa"] == "harness"
    assert [m.resultado for m in metricas.metricas if m.etapa == "diagnostico"] == ["harness"]
    assert encargo.especificaciones[0].intentos == 1  # no quemó el segundo intento

    # Reintentar sigue fallando (el cerebro no cambió): nueva duda, respondible.
    await lider.responder(creado.id, pregunta.id, "Reintentar")
    await lider.esperar(creado.id)
    [otra] = (await lider.obtener(creado.id)).preguntas_abiertas()
    assert otra.id != pregunta.id
    await lider.responder(creado.id, otra.id, "Descartar")
    await lider.esperar(creado.id)
    assert (await lider.obtener(creado.id)).estado == "fallido"


def test_la_plantilla_de_cualquier_py_compila() -> None:
    from app.agents.fabrica.implementador import plantilla
    from app.dominio.fabrica import Especificacion

    espec = Especificacion(
        "S6",
        'Página "web" del resumen',
        "d",
        archivos=["src/app.py", "tests/test_app.py", "e2e/test_panel.py", "otra/cosa.py"],
    )
    for ruta in espec.archivos:
        compile(plantilla(espec, ruta), ruta, "exec")
