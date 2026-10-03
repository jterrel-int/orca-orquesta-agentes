"""Modo "diseñar por especificaciones": intención, autocompletado, cobertura,
preguntas al estilo spec-kit (/clarify) y el pedido compuesto en EARS.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.agents.fabrica import AnalistaRequisitos, Medidor
from app.agents.fabrica.especificador import especificar_heuristicamente
from app.api.requisitos import obtener_analista, router
from app.dominio.fabrica import Consumo, RespuestaMedida
from app.dominio.requisitos import (
    MAX_MODULOS,
    MAX_PREGUNTAS,
    Modulo,
    RespuestaRequisito,
    a_ears,
    agrupar,
    analizar,
    componer_pedido,
    detectar_intencion,
    sugerir,
)

TIENDA = [
    "Registrar productos con nombre y precio",
    "Agregar productos al carrito",
    "Los clientes pueden ver sus pedidos",
]


def test_reconoce_la_intencion_del_proyecto() -> None:
    intencion = detectar_intencion(TIENDA)
    assert intencion.dominio == "tienda"
    assert "producto" in intencion.entidades
    assert intencion.confianza > 0.5
    assert detectar_intencion(["hacer algo genial"]).dominio is None


def test_autocompleta_la_frase_que_se_esta_escribiendo() -> None:
    s = sugerir(TIENDA[:2], "aplicar cup")
    assert s.autocompletado[0].startswith("Aplicar cupones")
    # Lo que ya está escrito no se vuelve a sugerir.
    assert not any("productos con nombre" in x for x in s.sugerencias)


def test_sin_dominio_igual_ofrece_completar_por_palabras() -> None:
    s = sugerir([], "registrar leads")
    assert any("leads" in x.lower() for x in s.autocompletado)


def test_agrupa_por_entidad_sin_perder_requisitos() -> None:
    modulos = agrupar(TIENDA)
    assert [m.nombre for m in modulos] == ["Productos", "Clientes"]
    assert sorted(i for m in modulos for i in m.requisitos) == [0, 1, 2]


def test_nunca_mas_de_seis_modulos() -> None:
    sueltos = [
        f"Gestionar {x}"
        for x in ("productos", "cupones", "leads", "reservas", "facturas", "tareas", "cursos", "x")
    ]
    modulos = agrupar(sueltos)
    assert len(modulos) <= MAX_MODULOS
    assert sorted(i for m in modulos for i in m.requisitos) == list(range(len(sueltos)))


def test_pregunta_lo_que_falta_con_una_opcion_recomendada() -> None:
    a = analizar(TIENDA)
    assert 0 < len(a.preguntas) <= MAX_PREGUNTAS
    assert a.cobertura["errores"] == "falta"
    assert not a.listo
    for p in a.preguntas:
        assert len(p.opciones) >= 2
        assert 0 <= p.recomendada < len(p.opciones)
        assert p.porque
    assert a.recomendaciones


def test_lo_respondido_no_se_vuelve_a_preguntar() -> None:
    primera = analizar(TIENDA)
    respuestas = [
        RespuestaRequisito(p.categoria, p.texto, p.opciones[p.recomendada])
        for p in primera.preguntas
    ]
    segunda = analizar(TIENDA, respuestas)
    assert segunda.preguntas == []
    assert segunda.listo
    assert all(segunda.cobertura[r.categoria] == "resuelta" for r in respuestas)


def test_ears() -> None:
    assert a_ears("Registrar productos.") == "EL SISTEMA DEBE registrar productos"
    assert a_ears("CUANDO falte el precio, EL SISTEMA DEBE avisar").startswith("CUANDO")
    assert a_ears("Los clientes ven sus pedidos") == (
        "EL SISTEMA DEBE garantizar que los clientes ven sus pedidos"
    )


def test_el_pedido_compuesto_se_vuelve_una_especificacion_por_modulo() -> None:
    respuestas = [RespuestaRequisito("usuarios", "¿Quién lo usa?", "Usuarios registrados")]
    pedido = componer_pedido(TIENDA, respuestas)
    assert pedido.startswith("Proyecto: ")
    assert "¿Quién lo usa? → Usuarios registrados" in pedido
    assert "- Módulo Productos: EL SISTEMA DEBE registrar productos" in pedido
    especs = especificar_heuristicamente(pedido, [])
    assert [e.titulo.split(":")[0] for e in especs] == ["Módulo Productos", "Módulo Clientes"]


def test_modulos_invalidos_se_reemplazan_por_los_deterministas() -> None:
    malos = [Modulo("Todo", [0])]  # pierde los requisitos 1 y 2
    pedido = componer_pedido(TIENDA, [], malos)
    assert "Módulo Clientes" in pedido


# --- el Analista ---


class CerebroAnalista(CerebroGuionado):
    def __init__(self, respuesta: dict[str, object]) -> None:
        self._respuesta = respuesta

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        return RespuestaMedida(json.dumps(self._respuesta), Consumo("falso", 1, 1, 0.001))


async def test_el_analista_usa_lo_que_valida_del_cerebro() -> None:
    cerebro = CerebroAnalista(
        {
            "intencion": {"resumen": "Una tienda online para un almacén de barrio."},
            "modulos": [
                {"nombre": "Catálogo", "requisitos": [0]},
                {"nombre": "Compra", "requisitos": [1, 2]},
            ],
            "preguntas": [
                {
                    "categoria": "pagos",
                    "texto": "¿Cómo se paga?",
                    "porque": "Cambia la integración",
                    "opciones": ["Efectivo", "Tarjeta"],
                    "recomendada": 1,
                }
            ],
            "recomendaciones": [{"texto": "Enviar un email al confirmar el pedido"}],
        }
    )
    a = await AnalistaRequisitos(cerebro).analizar(TIENDA, [], medidor=Medidor())
    assert a.origen == "cerebro"
    assert a.intencion.resumen == "Una tienda online para un almacén de barrio."
    assert [m.nombre for m in a.modulos] == ["Catálogo", "Compra"]
    assert a.preguntas[0].categoria == "general"  # "pagos" no es una categoría conocida
    assert a.recomendaciones[0].texto == "Enviar un email al confirmar el pedido"


async def test_el_analista_descarta_modulos_que_pierden_requisitos() -> None:
    cerebro = CerebroAnalista({"modulos": [{"nombre": "Todo", "requisitos": [0, 1]}]})
    a = await AnalistaRequisitos(cerebro).analizar(TIENDA, [], medidor=Medidor())
    assert sorted(i for m in a.modulos for i in m.requisitos) == [0, 1, 2]


async def test_con_el_guionado_el_analisis_es_el_determinista() -> None:
    a = await AnalistaRequisitos(CerebroGuionado()).analizar(TIENDA, [], medidor=Medidor())
    assert a.origen == "heuristica"
    assert a == analizar(TIENDA)


# --- la API ---


@pytest.fixture
async def cliente() -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[obtener_analista] = lambda: AnalistaRequisitos(CerebroGuionado())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_api_sugerir_analizar_y_componer(cliente: httpx.AsyncClient) -> None:
    base = "/api/fabrica/requisitos"
    r = await cliente.post(f"{base}/sugerir", json={"requisitos": TIENDA[:1], "borrador": "carr"})
    assert r.status_code == 200
    assert r.json()["intencion"]["dominio"] == "tienda"

    r = await cliente.post(f"{base}/analizar", json={"requisitos": TIENDA})
    analisis = r.json()
    assert analisis["preguntas"] and analisis["modulos"]

    pregunta = analisis["preguntas"][0]
    r = await cliente.post(
        f"{base}/componer",
        json={
            "requisitos": TIENDA,
            "respuestas": [
                {
                    "categoria": pregunta["categoria"],
                    "pregunta": pregunta["texto"],
                    "respuesta": pregunta["opciones"][pregunta["recomendada"]],
                }
            ],
            "modulos": analisis["modulos"],
            "resumen": analisis["intencion"]["resumen"],
        },
    )
    assert r.status_code == 200
    assert "Módulo Productos" in r.json()["pedido"]


async def test_api_rechaza_una_lista_vacia(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/api/fabrica/requisitos/analizar", json={"requisitos": []})
    assert r.status_code == 422
