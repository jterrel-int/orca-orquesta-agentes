"""Reglas puras de la fábrica: dependencias, política, bitácora sellada y
signos vitales. Nada de esto toca disco, red ni base de datos.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.dominio.fabrica import (
    HASH_GENESIS,
    Encargo,
    Especificacion,
    MetricaEtapa,
    PoliticaFabrica,
    Pregunta,
    aplicar_modo_aprobacion,
    encargo_desde_dict,
    estado_final,
    orden_topologico,
    presupuesto_agotado,
    primer_registro_roto,
    ruta_permitida,
    sellar,
    siguiente_especificacion,
    validar_dependencias,
)
from app.dominio.salud import calcular_signos_vitales, velocidad_historica


def _espec(id: str, *deps: str, estado: str = "pendiente") -> Especificacion:
    return Especificacion(id=id, titulo=id, descripcion="", depende_de=list(deps), estado=estado)  # type: ignore[arg-type]


def test_orden_topologico_respeta_dependencias() -> None:
    especs = [_espec("S3", "S1", "S2"), _espec("S1"), _espec("S2", "S1")]
    orden, ciclo = orden_topologico(especs)
    assert orden == ["S1", "S2", "S3"]
    assert ciclo == []


def test_validar_dependencias_detecta_ciclo_inexistente_y_autorreferencia() -> None:
    errores = validar_dependencias([_espec("S1", "S2"), _espec("S2", "S1"), _espec("S3", "S9")])
    assert any("circular" in e for e in errores)
    assert any("S9" in e for e in errores)
    assert validar_dependencias([_espec("S1", "S1")]) == ["S1 depende de sí misma"]


def test_siguiente_espera_a_las_dependencias_y_bloquea_si_fallan() -> None:
    encargo = Encargo(id="x", pedido="p", especificaciones=[_espec("S1"), _espec("S2", "S1")])
    assert siguiente_especificacion(encargo).id == "S1"  # type: ignore[union-attr]

    encargo.especificaciones[0].estado = "aprobada"
    assert siguiente_especificacion(encargo).id == "S2"  # type: ignore[union-attr]

    encargo.especificaciones[0].estado = "fallida"
    assert siguiente_especificacion(encargo) is None
    assert encargo.especificaciones[1].estado == "bloqueada"
    assert estado_final(encargo) == "fallido"


def test_ruta_permitida_confina_al_espacio_de_trabajo() -> None:
    p = PoliticaFabrica()
    assert ruta_permitida("src/modulo.py", p)
    assert ruta_permitida("tests/test_modulo.py", p)
    for mala in (
        "../src/x.py",
        "/etc/passwd",
        "C:/x.py",
        "src/../../x.py",
        "backend/app/main.py",
        "src/.env",
    ):
        assert not ruta_permitida(mala, p), mala


def test_bitacora_detecta_una_alteracion_y_desde_donde() -> None:
    r1 = sellar(1, "e", "implementador", "archivos_escritos", {"sha256": "aaa"}, HASH_GENESIS)
    r2 = sellar(2, "e", "revisor", "revision", {"aprobado": True}, r1.hash)
    r3 = sellar(3, "e", "verificador", "verificacion", {"aprobado": True}, r2.hash)
    assert primer_registro_roto([r1, r2, r3]) is None

    # Un agente "corrige" su evidencia después de los hechos.
    alterado = replace(r2, evidencia={"aprobado": False})
    assert primer_registro_roto([r1, alterado, r3]) == 2
    # Borrar un registro también rompe la cadena.
    assert primer_registro_roto([r1, r3]) == 3


def test_modo_nunca_decide_solo_y_deja_constancia() -> None:
    encargo = Encargo(
        id="x",
        pedido="p",
        especificaciones=[_espec("S1")],
        preguntas=[Pregunta("P-1", "¿Qué hago con items?", ["Reutilizar", "Nueva"])],
    )
    encargo.especificaciones[0].requiere_aprobacion = True
    decisiones = aplicar_modo_aprobacion(encargo, "nunca")
    assert decisiones == ["¿Qué hago con items? → Reutilizar"]
    assert encargo.preguntas_abiertas() == []
    assert not encargo.especificaciones[0].requiere_aprobacion


def test_modo_siempre_pide_aprobacion_para_todo() -> None:
    encargo = Encargo(id="x", pedido="p", especificaciones=[_espec("S1"), _espec("S2")])
    aplicar_modo_aprobacion(encargo, "siempre")
    assert all(e.requiere_aprobacion for e in encargo.especificaciones)


def test_presupuesto() -> None:
    encargo = Encargo(id="x", pedido="p", costo_usd=0.6)
    assert presupuesto_agotado(encargo, PoliticaFabrica(presupuesto_encargo_usd=0.5))
    assert not presupuesto_agotado(encargo, PoliticaFabrica(presupuesto_encargo_usd=0))


def test_encargo_ida_y_vuelta_por_dict_tolera_claves_viejas_y_nuevas() -> None:
    encargo = Encargo(
        id="x",
        pedido="p",
        especificaciones=[_espec("S1")],
        preguntas=[Pregunta("P-1", "¿?", ["a"])],
    )
    datos = encargo.a_dict()
    datos["clave_del_futuro"] = 1
    datos["especificaciones"][0]["otra_clave"] = True
    assert encargo_desde_dict(datos) == encargo


def test_signos_vitales_alertan_de_rechazos_humano_y_bitacora() -> None:
    ahora = datetime(2026, 9, 23, 12, tzinfo=UTC)
    aprobada = _espec("S1", estado="aprobada")
    aprobada.intentos = 1
    fallida = _espec("S2", estado="fallida")
    encargos = [
        Encargo(id="a", pedido="p", especificaciones=[aprobada, fallida], costo_usd=0.2,
                creado_en=ahora.isoformat()),
        Encargo(id="b", pedido="p", estado="esperando_humano", creado_en=ahora.isoformat()),
    ]  # fmt: skip
    metricas = [
        MetricaEtapa("a", "revision", "revisor", "rechazo", 1.0, ts=ahora.isoformat()),
        MetricaEtapa("a", "diagnostico", "diagnosticador", "harness", 0.5, ts=ahora.isoformat()),
    ]
    signos = calcular_signos_vitales(
        encargos, metricas, bitacora_integra=False, ahora=ahora, presupuesto_encargo_usd=1.0
    )
    assert signos.estado_general == "critico"
    signos_nombres = {a.signo for a in signos.alertas}
    assert {"bitacora", "rechazos", "harness", "humano"} <= signos_nombres
    assert signos.tasa_aprobacion_primer_intento == 0.5
    assert signos.rechazos_por_causa == {"harness": 1}
    assert signos.esperando_humano == 1


def test_signos_vitales_sanos() -> None:
    ahora = datetime(2026, 9, 23, 12, tzinfo=UTC)
    aprobada = _espec("S1", estado="aprobada")
    aprobada.intentos = 1
    encargos = [Encargo(id="a", pedido="p", estado="terminado", especificaciones=[aprobada],
                        creado_en=ahora.isoformat())]  # fmt: skip
    signos = calcular_signos_vitales(
        encargos, [], bitacora_integra=True, ahora=ahora, presupuesto_encargo_usd=1.0
    )
    assert signos.estado_general == "ok"
    assert signos.alertas == []


def test_velocidad_historica_incluye_dias_vacios() -> None:
    ahora = datetime(2026, 9, 23, 12, tzinfo=UTC)
    ayer = (ahora - timedelta(days=1)).isoformat()
    metricas = [
        MetricaEtapa("a", "verificacion", "verificador", "ok", 2.0, costo_usd=0.01, ts=ayer),
        MetricaEtapa("a", "implementacion", "implementador", "ok", 3.0, costo_usd=0.02, ts=ayer),
    ]
    puntos = velocidad_historica([], metricas, ahora=ahora, dias=3)
    assert [p.dia for p in puntos] == ["2026-09-21", "2026-09-22", "2026-09-23"]
    assert puntos[1].especificaciones_aprobadas == 1
    assert puntos[1].costo_usd == 0.03
    assert puntos[1].duracion_total_s == 5.0
    assert puntos[2].costo_usd == 0
