"""Piezas compartidas por los agentes de la fábrica."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from ...dominio.puertos import Cerebro, CerebroMedido


def limpiar_cercas(texto: str) -> str:
    """Quita las cercas de markdown que un LLM suele agregar pese a pedirle
    que no.
    """
    lineas = texto.strip().splitlines()
    if lineas and lineas[0].startswith("```"):
        lineas = lineas[1:]
    if lineas and lineas[-1].startswith("```"):
        lineas = lineas[:-1]
    return "\n".join(lineas) + "\n"


class Medidor:
    """Acumula lo que consumió una etapa. El Líder crea uno por etapa y lo
    convierte en una MetricaEtapa al terminar.

    Con un cerebro que no informa su consumo (claude-cli) estima ~4
    caracteres por token y deja el costo como desconocido — un costo
    inventado sería peor que un hueco.
    """

    def __init__(self) -> None:
        self.modelo = ""
        self.tokens_entrada = 0
        self.tokens_salida = 0
        self.costo_usd: float | None = 0.0
        # Caracteres que armar_contexto() recortó para entrar en el límite.
        self.compactado = 0

    async def pensar(
        self, cerebro: Cerebro, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> str:
        if isinstance(cerebro, CerebroMedido):
            r = await cerebro.pensar_medido(instruccion, contexto, respaldo=respaldo)
            texto, c = r.texto, r.consumo
            modelo, entrada, salida, costo = (
                c.modelo,
                c.tokens_entrada,
                c.tokens_salida,
                c.costo_usd,
            )
        else:
            texto = await cerebro.pensar(instruccion, contexto, respaldo=respaldo)
            modelo = str(getattr(cerebro, "nombre", "desconocido"))
            entrada = (len(instruccion) + len(contexto)) // 4
            salida = len(texto) // 4
            costo = None
        self.modelo = modelo
        self.tokens_entrada += entrada
        self.tokens_salida += salida
        self.costo_usd = (
            None if (self.costo_usd is None or costo is None) else self.costo_usd + costo
        )
        return texto


def extraer_json(texto: str) -> Any | None:
    """El primer objeto JSON del texto, o None. Tolera cercas de markdown y
    prosa alrededor — un LLM las agrega aunque se le pida que no.
    """
    limpio = limpiar_cercas(texto)
    inicio, fin = limpio.find("{"), limpio.rfind("}")
    if inicio < 0 or fin <= inicio:
        return None
    try:
        return json.loads(limpio[inicio : fin + 1])
    except ValueError:
        return None


def slug(texto: str, largo: int = 28) -> str:
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base.lower()).strip("_")
    return (base[:largo].rstrip("_")) or "modulo"


def palabras(texto: str) -> list[str]:
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9_]+", base.lower())


LIMITE_CONTEXTO = 60000
_MINIMO_TROZO = 400
_MARCA = "\n… [{n} caracteres omitidos por compactación] …\n"


def recortar_centro(texto: str, maximo: int) -> str:
    """Conserva cabeza y cola, que es donde suele estar lo útil: los imports
    y firmas de un archivo, el resumen final de una salida de pytest.
    """
    if len(texto) <= maximo:
        return texto
    marca = _MARCA.format(n=len(texto) - maximo)
    mitad = max(0, (maximo - len(marca)) // 2)
    return texto[:mitad] + marca + texto[len(texto) - mitad :]


def _hojas_de_texto(nodo: Any, ruta: tuple[Any, ...] = ()) -> list[tuple[tuple[Any, ...], str]]:
    if isinstance(nodo, str):
        return [(ruta, nodo)]
    if isinstance(nodo, dict):
        return [h for k, v in nodo.items() for h in _hojas_de_texto(v, (*ruta, k))]
    if isinstance(nodo, list):
        return [h for i, v in enumerate(nodo) for h in _hojas_de_texto(v, (*ruta, i))]
    return []


def armar_contexto(datos: dict[str, Any], limite: int, medidor: Medidor | None = None) -> str:
    """Serializa el contexto de una etapa y, si supera `limite` caracteres, lo
    compacta de forma determinista: recorta por el centro el texto más largo,
    una y otra vez, hasta que entra. Mismo contexto de entrada → mismo
    contexto compactado, así que la caché de respuestas sigue acertando.

    No resume con un LLM a propósito: un resumen generado puede inventar, y
    este contexto es la evidencia con la que trabaja el agente siguiente.
    """
    trabajo = json.loads(json.dumps(datos, ensure_ascii=False, default=str))
    texto = json.dumps(trabajo, ensure_ascii=False, indent=1)
    original = len(texto)
    for _ in range(64):
        exceso = len(texto) - limite
        if exceso <= 0:
            break
        hojas = [h for h in _hojas_de_texto(trabajo) if len(h[1]) > _MINIMO_TROZO]
        if not hojas:
            break
        ruta, valor = max(hojas, key=lambda h: len(h[1]))
        nuevo = recortar_centro(valor, max(_MINIMO_TROZO, len(valor) - exceso - 200))
        padre = trabajo
        for paso in ruta[:-1]:
            padre = padre[paso]
        padre[ruta[-1]] = nuevo
        texto = json.dumps(trabajo, ensure_ascii=False, indent=1)
    if medidor is not None and len(texto) < original:
        medidor.compactado += original - len(texto)
    return texto
