"""Modo "diseñar por especificaciones": sugerencias mientras se escribe,
análisis al terminar y composición del pedido para la fábrica.

Adaptador de entrada: traduce HTTP a dominio/requisitos.py (sugerir,
componer — deterministas, instantáneos y gratis) y al Analista (analizar —
usa el cerebro si hay uno). No crea el encargo: la persona revisa el pedido
compuesto y lo encarga con POST /api/fabrica/encargos, como cualquier otro.
"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..adaptadores.fabricas import construir_analista
from ..agents.fabrica import AnalistaRequisitos, Medidor
from ..dominio.requisitos import (
    Modulo,
    RespuestaRequisito,
    componer_pedido,
    sugerir,
)

router = APIRouter(prefix="/api/fabrica/requisitos", tags=["fábrica"])


class EntradaSugerir(BaseModel):
    requisitos: list[str] = Field(default_factory=list, max_length=60)
    borrador: str = Field(default="", max_length=500)


class EntradaRespuesta(BaseModel):
    categoria: str = Field(min_length=1, max_length=40)
    pregunta: str = Field(min_length=1, max_length=400)
    respuesta: str = Field(min_length=1, max_length=400)


class EntradaModulo(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    requisitos: list[int] = Field(max_length=60)


class EntradaAnalizar(BaseModel):
    requisitos: list[str] = Field(min_length=1, max_length=60)
    respuestas: list[EntradaRespuesta] = Field(default_factory=list, max_length=20)


class EntradaComponer(EntradaAnalizar):
    modulos: list[EntradaModulo] | None = Field(default=None, max_length=6)
    resumen: str = Field(default="", max_length=400)


async def obtener_analista() -> AnalistaRequisitos:
    return await construir_analista()


def _limpios(requisitos: list[str]) -> list[str]:
    return [r.strip()[:500] for r in requisitos if r.strip()]


def _respuestas(entrada: EntradaAnalizar) -> list[RespuestaRequisito]:
    return [RespuestaRequisito(r.categoria, r.pregunta, r.respuesta) for r in entrada.respuestas]


@router.post("/sugerir")
async def sugerir_requisitos(entrada: EntradaSugerir) -> dict[str, Any]:
    """Mientras se escribe: de qué va el proyecto y cómo completar la idea.
    Determinista y sin LLM: se llama en cada pausa del teclado.
    """
    return asdict(sugerir(_limpios(entrada.requisitos), entrada.borrador))


@router.post("/analizar")
async def analizar_requisitos(
    entrada: EntradaAnalizar, analista: AnalistaRequisitos = Depends(obtener_analista)
) -> dict[str, Any]:
    """Al decir "listo": agrupa, detecta la intención, mide la cobertura y
    devuelve preguntas (si falta algo) y recomendaciones para completar.
    """
    medidor = Medidor()
    analisis = await analista.analizar(
        _limpios(entrada.requisitos), _respuestas(entrada), medidor=medidor
    )
    return {**asdict(analisis), "costo_usd": medidor.costo_usd, "modelo": medidor.modelo}


@router.post("/componer")
async def componer(entrada: EntradaComponer) -> dict[str, str]:
    """El pedido final, listo para revisar y encargar."""
    modulos = [Modulo(m.nombre, m.requisitos) for m in entrada.modulos or []]
    return {
        "pedido": componer_pedido(
            _limpios(entrada.requisitos), _respuestas(entrada), modulos, entrada.resumen
        )
    }
