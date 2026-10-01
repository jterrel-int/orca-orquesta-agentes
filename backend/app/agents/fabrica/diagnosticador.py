"""Diagnosticador: agente efímero. El Líder lo crea solo cuando el Revisor
rechaza algo, y lo descarta apenas responde.

Su única pregunta: ¿de quién es la culpa?
- "harness": el entorno falló (no hay pytest, timeout, Docker caído). Reintentar
  el código no sirve; hace falta que una persona mire el entorno.
- "especificacion": la especificación es contradictoria o imposible, o el
  mismo rechazo se repite. Hace falta una decisión humana.
- "implementacion": el código está mal. El Implementador reintenta con el
  motivo del rechazo.

Primero reglas deterministas; el LLM solo decide la zona gris.
"""

from __future__ import annotations

import json
import re

from ...dominio.fabrica import CausaFallo, Diagnostico, Especificacion, Veredicto
from ...dominio.puertos import Cerebro
from .comun import LIMITE_CONTEXTO, Medidor, armar_contexto, extraer_json

_SENALES_HARNESS = (
    "No module named pytest",
    "No se encontró el ejecutable",
    "Comando no permitido",
    "Cannot connect to the Docker daemon",
    "Unable to find image",
    "Se superó el tiempo límite",
)
_CAUSAS: tuple[CausaFallo, ...] = ("especificacion", "harness", "implementacion")


_TIEMPO = re.compile(r"\bin \d+(?:\.\d+)?s\b")


def _sin_tiempos(motivo: str) -> str:
    """ "10 failed, 17 passed in 1.62s" y "... in 1.58s" son el mismo rechazo:
    sin esto la regla de "se repitió" nunca se cumplía con pytest.
    """
    return _TIEMPO.sub("", motivo).strip()


def diagnostico_determinista(
    veredicto: Veredicto, motivos_previos: list[str]
) -> Diagnostico | None:
    codigo = veredicto.evidencia.get("codigo_salida")
    salida = str(veredicto.evidencia.get("salida", ""))
    if codigo in (124, 127) or any(s in salida for s in _SENALES_HARNESS):
        return Diagnostico("harness", f"El entorno de verificación falló (código {codigo})")
    if veredicto.motivo.startswith("Especificación:"):
        return Diagnostico("especificacion", veredicto.motivo)
    if motivos_previos and _sin_tiempos(motivos_previos[-1]) == _sin_tiempos(veredicto.motivo):
        return Diagnostico(
            "especificacion",
            "El mismo rechazo se repitió después de corregir: probablemente la "
            "especificación pide algo contradictorio o imposible",
        )
    return None


class Diagnosticador:
    name = "diagnosticador"

    def __init__(self, cerebro: Cerebro, limite_contexto: int = LIMITE_CONTEXTO) -> None:
        self._cerebro = cerebro
        self._limite = limite_contexto

    async def diagnosticar(
        self,
        espec: Especificacion,
        veredicto: Veredicto,
        motivos_previos: list[str],
        *,
        medidor: Medidor,
    ) -> Diagnostico:
        regla = diagnostico_determinista(veredicto, motivos_previos)
        if regla is not None:
            return regla
        respaldo = Diagnostico("implementacion", "El código no cumple; se reintenta")
        crudo = await medidor.pensar(
            self._cerebro,
            "Sos el Diagnosticador de una fábrica de software. El Revisor rechazó una "
            "implementación. Decidí la causa: 'implementacion' (el código está mal), "
            "'especificacion' (la especificación es ambigua o contradictoria) o 'harness' "
            '(falla del entorno). Respondé SOLO JSON: {"causa": "...", "explicacion": "..."}.',
            armar_contexto(
                {
                    "especificacion": vars(espec),
                    "motivo_rechazo": veredicto.motivo,
                    "evidencia": veredicto.evidencia,
                    "rechazos_previos": motivos_previos,
                },
                self._limite,
                medidor,
            ),
            respaldo=json.dumps(vars(respaldo)),
        )
        datos = extraer_json(crudo)
        if isinstance(datos, dict):
            causa = datos.get("causa")
            for valida in _CAUSAS:
                if causa == valida:
                    return Diagnostico(valida, str(datos.get("explicacion") or ""))
        return respaldo
