"""Caché de respuestas del LLM, plugins de ciclo de vida y compactación de
contexto de la fábrica.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fabrica_falsos import EjecutorGuionado, construir_lider
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.adaptadores.persistencia_sqlalchemy as persistencia
from app.adaptadores.cache_llm import CerebroConCache, estado_cache, limpiar_cache
from app.agents.fabrica.comun import Medidor, armar_contexto, recortar_centro
from app.agents.fabrica.implementador import Implementador
from app.dominio.fabrica import Consumo, Especificacion, PoliticaFabrica, RespuestaMedida
from app.orchestrator.plugins import RegistroPlugins

# --- caché ---


class CerebroContado:
    def __init__(self, *, falla: bool = False) -> None:
        self.llamadas = 0
        self._falla = falla

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return (await self.pensar_medido(instruccion, contexto, respaldo=respaldo)).texto

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        self.llamadas += 1
        if self._falla:
            return RespuestaMedida(respaldo, Consumo("m"))
        return RespuestaMedida(f"respuesta {self.llamadas}", Consumo("m", 100, 50, 0.01))


@pytest.fixture
async def sesiones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    motor = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    fabrica = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(persistencia, "motor", motor)
    monkeypatch.setattr(persistencia, "FabricaSesion", fabrica)
    await persistencia.crear_tablas()
    yield fabrica
    await motor.dispose()


async def test_la_cache_no_repite_una_llamada_pagada(
    sesiones: async_sessionmaker[AsyncSession],
) -> None:
    interno = CerebroContado()
    cerebro = CerebroConCache(interno, "m", sesiones)

    primera = await cerebro.pensar_medido("instrucción", "contexto")
    segunda = await cerebro.pensar_medido("instrucción", "contexto")
    distinta = await cerebro.pensar_medido("instrucción", "otro contexto")

    assert interno.llamadas == 2
    assert segunda.texto == primera.texto == "respuesta 1"
    assert segunda.consumo == Consumo("cache:m", 0, 0, 0.0)
    assert distinta.texto == "respuesta 2"
    estado = await estado_cache(sesiones)
    assert estado == {
        "entradas": 2,
        "aciertos": 1,
        "ahorro_estimado_usd": 0.01,
        "tokens_ahorrados": 150,
    }
    assert await limpiar_cache(sesiones) == 2


async def test_la_cache_nunca_guarda_un_respaldo(
    sesiones: async_sessionmaker[AsyncSession],
) -> None:
    interno = CerebroContado(falla=True)
    cerebro = CerebroConCache(interno, "m", sesiones)
    await cerebro.pensar_medido("i", "c", respaldo="plan B")
    await cerebro.pensar_medido("i", "c", respaldo="plan B")
    assert interno.llamadas == 2
    assert (await estado_cache(sesiones))["entradas"] == 0


# --- plugins ---


async def test_plugins_reciben_los_eventos_del_ciclo(tmp_path: Path) -> None:
    plugins = RegistroPlugins()
    vistos: list[tuple[str, dict[str, Any]]] = []
    for evento in ("encargo_creado", "especificacion_aprobada", "encargo_terminado"):
        plugins.al(evento, lambda _e=evento, **datos: vistos.append((_e, datos)))

    lider, *_ = construir_lider(tmp_path)
    lider.plugins = plugins
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)

    assert [e for e, _ in vistos] == [
        "encargo_creado",
        "especificacion_aprobada",
        "encargo_terminado",
    ]
    assert vistos[-1][1]["estado"] == "terminado"


async def test_un_veto_se_reintenta_y_un_plugin_roto_no_tumba_el_encargo(
    tmp_path: Path,
) -> None:
    plugins = RegistroPlugins()
    vetos = iter(["usa eval()", None])
    plugins.compuerta("antes_de_aprobar", lambda **_: next(vetos))

    def explota(**_: object) -> None:
        raise RuntimeError("bum")

    plugins.al("especificacion_aprobada", explota)

    lider, _, bitacora, *_ = construir_lider(tmp_path)
    lider.plugins = plugins
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)
    encargo = await lider.obtener(creado.id)

    assert encargo.estado == "terminado", encargo.motivo
    assert encargo.especificaciones[0].intentos == 2
    assert "veto" in bitacora.acciones()
    error = next(r for r in bitacora.registros if r.accion == "plugin_error")
    assert "bum" in error.evidencia["errores"][0]


async def test_una_compuerta_que_falla_cuenta_como_veto() -> None:
    plugins = RegistroPlugins()

    def rota(**_: object) -> str:
        raise ValueError("sin acceso")

    plugins.compuerta("antes_de_aprobar", rota)
    veto = await plugins.evaluar("antes_de_aprobar", espec_id="S1")
    assert veto is not None and "sin acceso" in veto


def test_cargar_directorio_saltea_desactivados_y_registra_errores(tmp_path: Path) -> None:
    (tmp_path / "bueno.py").write_text(
        "def registrar(p):\n    p.al('encargo_creado', lambda **_: None)\n", encoding="utf-8"
    )
    (tmp_path / "_apagado.py").write_text("raise RuntimeError('no debería importarse')\n")
    (tmp_path / "sin_registrar.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "evento_malo.py").write_text(
        "def registrar(p):\n    p.al('no_existe', print)\n", encoding="utf-8"
    )

    plugins = RegistroPlugins()
    plugins.cargar_directorio(tmp_path)
    assert plugins.cargados == ["bueno"]
    assert len(plugins.errores) == 2


async def test_el_plugin_de_ejemplo_evalua(tmp_path: Path) -> None:
    ejemplo = Path(__file__).resolve().parent.parent / "plugins" / "_ejemplo_prohibir_eval.py"
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "prohibir_eval.py").write_text(
        ejemplo.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("def f(s):\n    return eval(s)\n")
    plugins = RegistroPlugins()
    plugins.cargar_directorio(tmp_path / "plugins")
    assert plugins.cargados == ["prohibir_eval"]
    veto = await plugins.evaluar(
        "antes_de_aprobar", encargo_id="e", espec_id="S1", espacio=tmp_path, archivos=["src/x.py"]
    )
    assert veto is not None and "src/x.py:2 usa eval()" in veto


# --- compactación de contexto ---


def test_recortar_centro_conserva_cabeza_y_cola() -> None:
    texto = "INICIO" + "x" * 5000 + "FINAL"
    recortado = recortar_centro(texto, 500)
    assert len(recortado) <= 500
    assert recortado.startswith("INICIO") and recortado.endswith("FINAL")
    assert "caracteres omitidos" in recortado


def test_armar_contexto_entra_en_el_limite_y_es_determinista() -> None:
    datos = {
        "especificacion": {"id": "S1", "titulo": "corto"},
        "archivos_actuales": {"src/a.py": "a" * 30000, "src/b.py": "b" * 20000},
    }
    medidor = Medidor()
    compacto = armar_contexto(datos, 12000, medidor)
    assert len(compacto) <= 12000
    assert compacto == armar_contexto(datos, 12000)
    assert json.loads(compacto)["especificacion"] == {"id": "S1", "titulo": "corto"}
    assert medidor.compactado > 0

    chico = armar_contexto({"a": "b"}, 12000, medidor := Medidor())
    assert json.loads(chico) == {"a": "b"} and medidor.compactado == 0


class CerebroEspia:
    def __init__(self) -> None:
        self.contextos: list[str] = []

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        self.contextos.append(contexto)
        return respaldo


async def test_el_reintento_recibe_el_historial_compacto(tmp_path: Path) -> None:
    espia = CerebroEspia()
    espec = Especificacion("S1", "t", "d", archivos=["src/modulo.py", "tests/test_modulo.py"])
    historial: list[dict[str, object]] = [
        {"intento": 1, "causa": "implementacion", "motivo": "falló", "archivos": ["src/modulo.py"]}
    ]
    await Implementador(espia).implementar(
        espec,
        tmp_path,
        PoliticaFabrica(),
        motivo_rechazo="falló",
        medidor=Medidor(),
        historial=historial,
    )
    assert json.loads(espia.contextos[0])["intentos_previos"] == historial


async def test_el_lider_pasa_el_historial_de_intentos(tmp_path: Path) -> None:
    lider, _, bitacora, *_ = construir_lider(tmp_path, ejecutor=EjecutorGuionado([1, 0]))
    creado = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(creado.id)
    escritos = [r for r in bitacora.registros if r.accion == "archivos_escritos"]
    assert len(escritos) == 2
    assert all("contexto_compactado" in r.evidencia for r in escritos)
