"""Analista de requisitos: el agente del modo "diseñar por especificaciones".

Recibe la lista de requisitos que escribió una persona (y lo que ya
respondió) y devuelve el análisis: intención, módulos, preguntas de
aclaración y recomendaciones para completar la especificación.

Primero corre el análisis determinista del dominio (dominio/requisitos.py) y
se lo pasa al cerebro como respaldo y punto de partida; el LLM solo puede
mejorarlo. Lo que devuelve se valida: los módulos tienen que repartir
exactamente los requisitos originales (por índice, así nunca se pierde ni se
reescribe lo que escribió la persona), como mucho 5 preguntas y cada una con
opciones y una recomendada válida. Lo que no pasa la validación se descarta y
queda la versión determinista.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any

from ...dominio.puertos import Cerebro
from ...dominio.requisitos import (
    MAX_PREGUNTAS,
    AnalisisRequisitos,
    Modulo,
    PreguntaRequisito,
    Recomendacion,
    RespuestaRequisito,
    analizar,
    categoria,
    modulos_validos,
)
from .comun import LIMITE_CONTEXTO, Medidor, armar_contexto, extraer_json


def _instruccion() -> str:
    return (
        "Sos el Analista de requisitos de una fábrica de software. Una persona escribió "
        "una lista de requisitos para un sistema nuevo. Partí del analisis_base y "
        "mejoralo:\n"
        "- resumen: una o dos oraciones con qué es el sistema y para quién;\n"
        "- modulos: agrupá los requisitos por funcionalidad (máximo 6), referenciándolos "
        "por su índice en la lista; cada índice en exactamente un módulo;\n"
        f"- preguntas: como máximo {MAX_PREGUNTAS}, solo sobre lo que cambia de verdad la "
        "arquitectura, los datos, la interfaz o las pruebas y que la persona no haya "
        "respondido ya; cada una con 2 a 4 opciones, el índice de la opción recomendada "
        "y por qué importa;\n"
        "- recomendaciones: requisitos concretos y verificables que faltan para que la "
        "especificación esté completa (máximo 8), en el formato 'CUANDO …, EL SISTEMA "
        "DEBE …' cuando haya una condición.\n"
        "Respondé SOLO un objeto JSON con la misma forma que analisis_base, en español."
    )


def _modulos(datos: Any, n: int) -> list[Modulo] | None:
    if not isinstance(datos, list):
        return None
    try:
        modulos = [
            Modulo(str(m["nombre"]).strip()[:60], [int(i) for i in m["requisitos"]])
            for m in datos
            if isinstance(m, dict)
        ]
    except (KeyError, TypeError, ValueError):
        return None
    return modulos if modulos_validos(modulos, n) else None


def _preguntas(datos: Any, respondidas: set[str]) -> list[PreguntaRequisito] | None:
    if not isinstance(datos, list):
        return None
    preguntas: list[PreguntaRequisito] = []
    for i, p in enumerate(datos[:MAX_PREGUNTAS]):
        if not isinstance(p, dict):
            return None
        opciones = [str(o).strip() for o in p.get("opciones", []) if str(o).strip()][:4]
        recomendada = p.get("recomendada", 0)
        texto = str(p.get("texto", "")).strip()
        clave = str(p.get("categoria", "")).strip() or "general"
        if not texto or len(opciones) < 2 or not isinstance(recomendada, int):
            return None
        if not 0 <= recomendada < len(opciones) or clave in respondidas:
            continue
        preguntas.append(
            PreguntaRequisito(
                f"{clave}-{i + 1}",
                clave,
                texto[:300],
                str(p.get("porque", "")).strip()[:300],
                opciones,
                recomendada,
            )
        )
    return preguntas


def _recomendaciones(datos: Any) -> list[Recomendacion] | None:
    if not isinstance(datos, list):
        return None
    resultado = [
        Recomendacion(
            str(r["texto"]).strip()[:300],
            str(r.get("categoria", "alcance")),
            str(r.get("porque", "")).strip()[:300],
        )
        for r in datos[:8]
        if isinstance(r, dict) and str(r.get("texto", "")).strip()
    ]
    return resultado or None


class AnalistaRequisitos:
    name = "analista"

    def __init__(self, cerebro: Cerebro, limite_contexto: int = LIMITE_CONTEXTO) -> None:
        self._cerebro = cerebro
        self._limite = limite_contexto

    async def analizar(
        self,
        requisitos: list[str],
        respuestas: list[RespuestaRequisito],
        *,
        medidor: Medidor,
    ) -> AnalisisRequisitos:
        requisitos = [r.strip() for r in requisitos if r.strip()]
        base = analizar(requisitos, respuestas)
        respaldo = json.dumps(asdict(base), ensure_ascii=False)
        contexto = armar_contexto(
            {
                "requisitos": dict(enumerate(requisitos)),
                "respuestas_ya_dadas": [asdict(r) for r in respuestas],
                "analisis_base": asdict(base),
            },
            self._limite,
            medidor,
        )
        crudo = await medidor.pensar(self._cerebro, _instruccion(), contexto, respaldo=respaldo)
        if crudo == respaldo:
            return base
        datos = extraer_json(crudo)
        if not isinstance(datos, dict):
            return base

        respondidas = {r.categoria for r in respuestas}
        modulos = _modulos(datos.get("modulos"), len(requisitos)) or base.modulos
        preguntas = _preguntas(datos.get("preguntas"), respondidas)
        if preguntas is None:
            preguntas = base.preguntas
        recomendaciones = _recomendaciones(datos.get("recomendaciones")) or base.recomendaciones
        resumen = str((datos.get("intencion") or {}).get("resumen", "")).strip()
        intencion = replace(base.intencion, resumen=resumen[:400]) if resumen else base.intencion
        # La cobertura sigue siendo la determinista; una categoría que el LLM
        # inventa queda como "general".
        preguntas = [
            p if categoria(p.categoria) else replace(p, categoria="general") for p in preguntas
        ]
        return AnalisisRequisitos(
            intencion=intencion,
            modulos=modulos,
            cobertura=base.cobertura,
            preguntas=preguntas,
            recomendaciones=recomendaciones,
            listo=bool(requisitos) and not preguntas,
            origen="cerebro",
        )
