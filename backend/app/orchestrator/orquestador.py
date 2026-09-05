"""Orquestación de agentes.

Diseño: una corrida es una lista de *etapas*, y cada etapa una lista de agentes
que corren juntos con asyncio.gather. Hoy son tres etapas de un agente cada una,
o sea puro secuencial. Para paralelizar backend y frontend basta con ponerlos en
la misma etapa — no hay que tocar los agentes ni el bus.

    ETAPAS = [[BackendAgent(), FrontendAgent()], [DeployAgent()]]

El orquestador decide el cuándo. Los agentes deciden el qué. Nunca al revés.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from ..adaptadores.bus_memoria import bus
from ..agents.backend_agent import BackendAgent
from ..agents.base import Agente, ContextoCorrida, ResultadoAgente
from ..agents.deploy_agent import DeployAgent
from ..agents.frontend_agent import FrontendAgent
from ..dominio.modelos import EstadoAgente, EventoAgente, ResumenCorrida
from ..dominio.puertos import PublicadorEventos

log = logging.getLogger(__name__)


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Orquestador:
    def __init__(self, bus_eventos: PublicadorEventos | None = None) -> None:
        self._bus = bus_eventos or bus
        self._corriendo = False
        self._lock = asyncio.Lock()
        self._resumen: ResumenCorrida | None = None

    # --- definición del pipeline ---

    def etapas(self) -> list[list[Agente]]:
        """Backend → Frontend → Deploy.

        Mueve dos agentes a la misma lista y correrán en paralelo.
        """
        return [[BackendAgent(), FrontendAgent()], [DeployAgent()]]

    # --- estado ---

    @property
    def corriendo(self) -> bool:
        return self._corriendo

    @property
    def resumen(self) -> ResumenCorrida | None:
        return self._resumen

    # --- ejecución ---

    async def ejecutar(self) -> ResumenCorrida:
        """Corre el pipeline completo. Una sola corrida a la vez."""
        async with self._lock:
            if self._corriendo:
                raise RuntimeError("Ya hay una corrida en curso")
            self._corriendo = True

        run_id = uuid.uuid4().hex[:8]
        etapas = self.etapas()
        nombres = [a.name for etapa in etapas for a in etapa]

        self._resumen = ResumenCorrida(
            run_id=run_id,
            status="running",
            agentes=[EstadoAgente(agent=n) for n in nombres],
            iniciado_en=_ahora_iso(),
        )

        ctx = ContextoCorrida(run_id=run_id, emitir=self._bus.publicar)
        await self._bus.publicar(
            EventoAgente(agent="orchestrator", status="running",
                         msg=f"Corrida {run_id} iniciada · {len(etapas)} etapas", run_id=run_id)
        )

        hubo_error = False
        try:
            for i, etapa in enumerate(etapas, start=1):
                if hubo_error:
                    for agente in etapa:
                        self._marcar(agente.name, "pending", "Omitido por fallo previo")
                        await self._bus.publicar(
                            EventoAgente(agent=agente.name, status="error",
                                         msg="Omitido: una etapa anterior falló", run_id=run_id)
                        )
                    continue

                etiqueta = ", ".join(a.name for a in etapa)
                await self._bus.publicar(
                    EventoAgente(agent="orchestrator", status="running",
                                 msg=f"Etapa {i}/{len(etapas)}: {etiqueta}", run_id=run_id)
                )

                resultados = await asyncio.gather(
                    *(agente.correr(ctx) for agente in etapa), return_exceptions=True
                )

                for agente, resultado in zip(etapa, resultados, strict=True):
                    if isinstance(resultado, BaseException):
                        # `correr` ya captura Exception; esto atrapa lo demás
                        # (por ejemplo, una cancelación) sin dejar la corrida colgada.
                        log.exception("Fallo no capturado en %s", agente.name)
                        self._marcar(agente.name, "error", str(resultado))
                        hubo_error = True
                        continue
                    self._aplicar(resultado)
                    if resultado.status == "error":
                        hubo_error = True

            estado_final = "error" if hubo_error else "done"
            self._resumen.status = estado_final
            self._resumen.terminado_en = _ahora_iso()

            await self._bus.publicar(
                EventoAgente(
                    agent="orchestrator",
                    status=estado_final,
                    msg=f"Corrida {run_id} {'con fallos' if hubo_error else 'completa'}",
                    run_id=run_id,
                )
            )
            return self._resumen
        finally:
            self._corriendo = False

    # --- helpers de estado ---

    def _aplicar(self, resultado: ResultadoAgente) -> None:
        for est in self._resumen.agentes:  # type: ignore[union-attr]
            if est.agent == resultado.agent:
                est.status = resultado.status
                est.ultimo_msg = resultado.msg
                est.duracion_s = round(resultado.duracion_s, 2)

    def _marcar(self, nombre: str, estado: str, msg: str) -> None:
        for est in self._resumen.agentes:  # type: ignore[union-attr]
            if est.agent == nombre:
                est.status = estado  # type: ignore[assignment]
                est.ultimo_msg = msg


orquestador = Orquestador()
