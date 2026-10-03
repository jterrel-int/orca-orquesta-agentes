"""Dobles en memoria para probar el Líder de la fábrica sin SQLite."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.adaptadores.ejecutor_pruebas import EjecutorLocal
from app.dominio.fabrica import (
    HASH_GENESIS,
    Consumo,
    Encargo,
    MetricaEtapa,
    PoliticaFabrica,
    RegistroBitacora,
    RespuestaMedida,
    ResultadoComando,
    sellar,
)
from app.dominio.modelos import EventoAgente
from app.dominio.puertos import Cerebro, EjecutorPruebas, EmisorLinea
from app.orchestrator.lider import LiderFabrica


class RepoEncargosMemoria:
    def __init__(self) -> None:
        self.datos: dict[str, Encargo] = {}

    async def guardar(self, encargo: Encargo) -> None:
        self.datos[encargo.id] = copy.deepcopy(encargo)

    async def obtener(self, encargo_id: str) -> Encargo | None:
        e = self.datos.get(encargo_id)
        return copy.deepcopy(e) if e else None

    async def listar(self) -> list[Encargo]:
        return [copy.deepcopy(e) for e in self.datos.values()]


class BitacoraMemoria:
    def __init__(self) -> None:
        self.registros: list[RegistroBitacora] = []

    async def registrar(
        self, encargo_id: str, agente: str, accion: str, evidencia: dict[str, Any]
    ) -> RegistroBitacora:
        previo = self.registros[-1].hash if self.registros else HASH_GENESIS
        r = sellar(len(self.registros) + 1, encargo_id, agente, accion, evidencia, previo)
        self.registros.append(r)
        return r

    async def listar(self, encargo_id: str | None = None) -> list[RegistroBitacora]:
        return [r for r in self.registros if encargo_id is None or r.encargo_id == encargo_id]

    def acciones(self) -> list[str]:
        return [r.accion for r in self.registros]


class MetricasMemoria:
    def __init__(self) -> None:
        self.metricas: list[MetricaEtapa] = []

    async def registrar(self, metrica: MetricaEtapa) -> None:
        self.metricas.append(metrica)

    async def listar(self, encargo_id: str | None = None) -> list[MetricaEtapa]:
        return [m for m in self.metricas if encargo_id is None or m.encargo_id == encargo_id]


class BusMemoria:
    def __init__(self) -> None:
        self.eventos: list[EventoAgente] = []

    async def publicar(self, evento: EventoAgente) -> None:
        self.eventos.append(evento)


class EjecutorGuionado:
    """Devuelve códigos de salida en orden; después del último, repite el último."""

    def __init__(self, codigos: list[int], salida: str = "") -> None:
        self._codigos = codigos
        self._salida = salida
        self.llamadas = 0

    async def ejecutar(
        self, directorio: str, comando: list[str], timeout_s: float
    ) -> ResultadoComando:
        codigo = self._codigos[min(self.llamadas, len(self._codigos) - 1)]
        self.llamadas += 1
        salida = self._salida or ("1 passed" if codigo == 0 else "FAILED tests/x.py - assert")
        return ResultadoComando(comando, codigo, salida, 0.01, "falso")


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


class CerebroCaro(CerebroGuionado):
    """Guionado que cobra: para probar el tope de presupuesto."""

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        # Modelo "guionado": devuelve la plantilla a propósito, no es un
        # cerebro real que falló (eso lo detecta el Implementador por el nombre).
        return RespuestaMedida(respaldo, Consumo("guionado", 1000, 1000, 0.4))


class DesplegadorFalso:
    def __init__(self) -> None:
        self.llamado = False

    async def ejecutar(self, on_linea: EmisorLinea) -> str | None:
        self.llamado = True
        await on_linea("simulado")
        return None


def construir_lider(
    tmp_path: Path,
    *,
    politica: PoliticaFabrica | None = None,
    ejecutor: EjecutorPruebas | None = None,
    cerebro: Cerebro | None = None,
    tablas: list[str] | None = None,
) -> tuple[LiderFabrica, RepoEncargosMemoria, BitacoraMemoria, MetricasMemoria, BusMemoria]:
    repo, bitacora, metricas, bus = (
        RepoEncargosMemoria(),
        BitacoraMemoria(),
        MetricasMemoria(),
        BusMemoria(),
    )
    desplegador = DesplegadorFalso()

    async def cerebro_para(_rol: str) -> Cerebro:
        return cerebro or CerebroGuionado()

    async def listar_tablas() -> list[str]:
        return tablas or []

    lider = LiderFabrica(
        repositorio=repo,
        bitacora=bitacora,
        metricas=metricas,
        bus=bus,
        politica=politica or PoliticaFabrica(),
        dir_espacios=tmp_path / "espacios",
        cerebro_para=cerebro_para,
        ejecutor=ejecutor or EjecutorLocal(),
        ejecutor_e2e=None,
        desplegador_para=lambda _espacio, _id, _titulo: desplegador,
        tablas_existentes=listar_tablas,
        timeout_pruebas_s=60,
    )
    return lider, repo, bitacora, metricas, bus
