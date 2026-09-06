"""Orden de las etapas y comportamiento ante un fallo en una etapa previa."""

from __future__ import annotations

from app.agents.base import Agente, ContextoCorrida
from app.dominio.modelos import EventoAgente
from app.orchestrator.orquestador import Orquestador


class BusFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoAgente] = []

    async def publicar(self, evento: EventoAgente) -> None:
        self.eventos.append(evento)


class AgenteFalso(Agente):
    def __init__(
        self, name: str, *, falla: bool = False, registro: list[str] | None = None
    ) -> None:
        self.name = name
        self._falla = falla
        self._registro = registro

    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        if self._registro is not None:
            self._registro.append(self.name)
        if self._falla:
            raise RuntimeError(f"{self.name} falló a propósito")
        return []


class OrquestadorDePrueba(Orquestador):
    def __init__(self, etapas: list[list[Agente]], bus_eventos: BusFalso) -> None:
        super().__init__(bus_eventos)
        self._etapas_prueba = etapas

    def etapas(self) -> list[list[Agente]]:
        return self._etapas_prueba


async def test_etapas_corren_en_orden() -> None:
    orden: list[str] = []
    a = AgenteFalso("uno", registro=orden)
    b = AgenteFalso("dos", registro=orden)
    orq = OrquestadorDePrueba([[a], [b]], BusFalso())

    resumen = await orq.ejecutar()

    assert orden == ["uno", "dos"]
    assert resumen.status == "done"


async def test_fallo_en_etapa_1_omite_etapa_2() -> None:
    orden: list[str] = []
    a = AgenteFalso("uno", falla=True, registro=orden)
    b = AgenteFalso("dos", registro=orden)
    orq = OrquestadorDePrueba([[a], [b]], BusFalso())

    resumen = await orq.ejecutar()

    assert resumen.status == "error"
    assert orden == ["uno"]  # "dos" nunca se ejecutó

    estado_b = next(e for e in resumen.agentes if e.agent == "dos")
    assert estado_b.status == "pending"


# --- BE-05: caso_de_uso viaja al contexto y al resumen ---


async def test_ejecutar_propaga_caso_de_uso_al_contexto_y_al_resumen() -> None:
    capturado: list[str | None] = []

    class AgenteQueLeeElCaso(Agente):
        name = "backend"

        async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
            capturado.append(ctx.datos.get("caso_de_uso"))
            return []

    orq = OrquestadorDePrueba([[AgenteQueLeeElCaso()]], BusFalso())

    resumen = await orq.ejecutar(caso_de_uso="calculadora")

    assert capturado == ["calculadora"]
    assert resumen.caso_de_uso == "calculadora"


async def test_ejecutar_sin_caso_de_uso_deja_el_resumen_en_none() -> None:
    orq = OrquestadorDePrueba([[AgenteFalso("uno")]], BusFalso())

    resumen = await orq.ejecutar()

    assert resumen.caso_de_uso is None
