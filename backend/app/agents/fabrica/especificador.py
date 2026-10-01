"""Especificador: descompone un pedido en especificaciones pequeñas, con
dependencias y compuertas humanas, y pregunta cuando hay ambigüedad.

Con un cerebro real, el LLM propone; con el guionado (o si el LLM devuelve
algo inválido) se usa una descomposición heurística determinista. En los dos
casos el resultado pasa por las mismas validaciones: rutas permitidas por la
política, dependencias sin ciclos, al menos un archivo de pruebas por
especificación.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ...dominio.fabrica import (
    Especificacion,
    PoliticaFabrica,
    Pregunta,
    ruta_permitida,
    validar_dependencias,
)
from ...dominio.puertos import Cerebro
from .comun import LIMITE_CONTEXTO, Medidor, armar_contexto, extraer_json, palabras, slug

_RIESGO = (
    "pago", "pagos", "cobro", "cobrar", "eliminar", "borrar", "produccion",
    "migracion", "migrar", "contrasena", "password", "permisos", "facturacion",
)  # fmt: skip
_INTERFAZ = (
    "pantalla", "formulario", "pagina", "interfaz", "boton", "vista", "ui", "panel",
)  # fmt: skip
_OPCIONES_TABLA = [
    "Reutilizar la tabla existente",
    "Extenderla con columnas nuevas",
    "Crear una tabla nueva separada",
]
MAX_ESPECIFICACIONES = 6


def _id_pregunta(texto: str) -> str:
    return "P-" + hashlib.sha1(texto.encode("utf-8")).hexdigest()[:6]


def _trozos(pedido: str) -> list[str]:
    lineas = [ln.strip() for ln in pedido.splitlines() if ln.strip()]
    vinetas = [
        re.sub(r"^([-*•]|\d+[.)])\s*", "", ln) for ln in lineas if re.match(r"^([-*•]|\d+[.)])", ln)
    ]
    if len(vinetas) >= 2:
        candidatos = vinetas
    else:
        candidatos = [t.strip() for t in re.split(r"(?<=[.;])\s+|\n+", pedido) if t.strip()]
    utiles = [c.rstrip(".;") for c in candidatos if len(palabras(c)) >= 3]
    return (utiles or [pedido.strip()])[:MAX_ESPECIFICACIONES]


def preguntas_por_ambiguedad(pedido: str, tablas: list[str]) -> list[Pregunta]:
    """Reglas deterministas: estas preguntas aparecen con cualquier cerebro,
    porque un LLM puede pasarlas por alto y el costo de adivinar es alto.
    """
    vocab = set(palabras(pedido))
    preguntas: list[Pregunta] = []
    for tabla in tablas:
        variantes = {tabla.lower(), tabla.lower().rstrip("s"), tabla.lower() + "s"}
        if vocab & variantes:
            texto = (
                f"El pedido menciona «{tabla}», y ya existe una tabla legada con ese nombre. "
                "¿Qué hago con ella?"
            )
            preguntas.append(Pregunta(_id_pregunta(texto), texto, list(_OPCIONES_TABLA)))
    if len(vocab) < 4:
        texto = "El pedido es muy breve para especificarlo sin adivinar. ¿Qué debería hacer?"
        preguntas.append(
            Pregunta(
                _id_pregunta(texto),
                texto,
                ["Seguir con una interpretación mínima", "Lo detallo en la respuesta"],
            )
        )
    return preguntas


def especificar_heuristicamente(pedido: str, decisiones: list[str]) -> list[Especificacion]:
    especs: list[Especificacion] = []
    usados: set[str] = set()
    for i, trozo in enumerate(_trozos(pedido), start=1):
        base = slug(trozo)
        nombre = base if base not in usados else f"{base}_{i}"
        usados.add(nombre)
        vocab = set(palabras(trozo))
        e2e = bool(vocab & set(_INTERFAZ))
        archivos = [f"src/{nombre}.py", f"tests/test_{nombre}.py"]
        if e2e:
            archivos.append(f"e2e/{nombre}.spec.ts")
        descripcion = trozo
        if decisiones:
            descripcion += "\n\nDecisiones humanas: " + "; ".join(decisiones)
        especs.append(
            Especificacion(
                id=f"S{i}",
                titulo=trozo[:80],
                descripcion=descripcion,
                criterios=[
                    f"src/{nombre}.py expone una función pública `ejecutar_{nombre}`",
                    "Las pruebas unitarias de tests/ pasan",
                    "Cada función pública tiene al menos una prueba que la usa",
                ],
                archivos=archivos,
                # S1 es la base; el resto solo depende de ella, así que S2…Sn
                # corren en paralelo. Encadenarlas en fila sería más seguro y
                # mucho más lento — con el LLM, el Especificador decide mejor.
                depende_de=["S1"] if i > 1 else [],
                requiere_aprobacion=bool(vocab & set(_RIESGO)),
                e2e=e2e,
            )
        )
    return especs


def _instruccion() -> str:
    return (
        "Sos el Especificador de una fábrica de software. Descomponé el pedido en "
        f"especificaciones pequeñas (máximo {MAX_ESPECIFICACIONES}), cada una "
        "implementable y verificable por separado. Respondé SOLO un objeto JSON:\n"
        '{"preguntas": [{"texto": "...", "opciones": ["...", "..."]}],\n'
        ' "especificaciones": [{"id": "S1", "titulo": "...", "descripcion": "...",\n'
        '   "criterios": ["..."], "archivos": ["src/x.py", "tests/test_x.py"],\n'
        '   "depende_de": [], "requiere_aprobacion": false, "e2e": false}]}\n'
        "Reglas: los archivos solo pueden estar bajo src/, tests/, frontend/ o e2e/; "
        "cada especificación incluye al menos un tests/test_*.py; el código Python va "
        "en src/ y las pruebas lo importan como `from src.modulo import ...`. "
        "Declará en depende_de solo las dependencias reales: las especificaciones sin "
        "dependencias entre sí se construyen en paralelo. "
        "Las pruebas funcionales de interfaz van en e2e/<nombre>.spec.ts (Playwright con "
        "TypeScript), nunca en .py. "
        "Marcá requiere_aprobacion cuando toque dinero, datos de producción, borrado o "
        "permisos. Poné e2e=true solo si hay interfaz de usuario. Si el pedido choca "
        "con una tabla existente o es ambiguo, agregá una pregunta en vez de adivinar. "
        "Si el contexto trae una version_base, este pedido es una iteración sobre ese "
        "código: especificá solo el cambio, y cuando toque algo que ya existe usá la "
        "misma ruta de archivo para modificarlo en vez de crear uno nuevo. "
        "Escribí todo en español."
    )


def _desde_json(datos: Any, politica: PoliticaFabrica) -> list[Especificacion] | None:
    if not isinstance(datos, dict) or not isinstance(datos.get("especificaciones"), list):
        return None
    especs: list[Especificacion] = []
    for crudo in datos["especificaciones"][:MAX_ESPECIFICACIONES]:
        if not isinstance(crudo, dict):
            return None
        try:
            archivos = [str(a) for a in crudo.get("archivos", [])]
            e = Especificacion(
                id=str(crudo["id"]),
                titulo=str(crudo["titulo"])[:120],
                descripcion=str(crudo.get("descripcion", "")),
                criterios=[str(c) for c in crudo.get("criterios", [])],
                archivos=archivos,
                depende_de=[str(d) for d in crudo.get("depende_de", [])],
                requiere_aprobacion=bool(crudo.get("requiere_aprobacion", False)),
                e2e=bool(crudo.get("e2e", False)),
            )
        except (KeyError, TypeError):
            return None
        if not archivos or not all(ruta_permitida(a, politica) for a in archivos):
            return None
        if not any(a.startswith("tests/") and a.endswith(".py") for a in archivos):
            return None
        especs.append(e)
    if not especs or validar_dependencias(especs):
        return None
    return especs


def _preguntas_desde_json(datos: Any) -> list[Pregunta]:
    if not isinstance(datos, dict) or not isinstance(datos.get("preguntas"), list):
        return []
    preguntas: list[Pregunta] = []
    for p in datos["preguntas"][:3]:
        if isinstance(p, dict) and str(p.get("texto", "")).strip():
            texto = str(p["texto"]).strip()
            opciones = [str(o) for o in p.get("opciones", []) if str(o).strip()][:4]
            preguntas.append(Pregunta(_id_pregunta(texto), texto, opciones))
    return preguntas


class Especificador:
    name = "especificador"

    def __init__(self, cerebro: Cerebro, limite_contexto: int = LIMITE_CONTEXTO) -> None:
        self._cerebro = cerebro
        self._limite = limite_contexto

    async def especificar(
        self,
        pedido: str,
        *,
        tablas: list[str],
        respondidas: list[Pregunta],
        politica: PoliticaFabrica,
        medidor: Medidor,
        version_base: dict[str, object] | None = None,
    ) -> tuple[list[Especificacion], list[Pregunta], str]:
        """Devuelve (especificaciones, preguntas nuevas, origen).

        `version_base`, si viene, describe la versión de la que parte esta
        iteración (pedido anterior, especificaciones y archivos existentes):
        se especifica solo el cambio, sobre ese código.
        """
        decisiones = [f"{p.texto} → {p.respuesta}" for p in respondidas]
        respaldo = especificar_heuristicamente(pedido, decisiones)
        contexto = armar_contexto(
            {
                "pedido": pedido,
                "tablas_existentes": tablas,
                "decisiones_humanas": decisiones,
                "version_base": version_base,
            },
            self._limite,
            medidor,
        )
        respaldo_json = json.dumps(
            {"preguntas": [], "especificaciones": [vars(e) for e in respaldo]},
            ensure_ascii=False,
        )
        crudo = await medidor.pensar(
            self._cerebro, _instruccion(), contexto, respaldo=respaldo_json
        )
        datos = extraer_json(crudo)
        especs = _desde_json(datos, politica)
        origen = "cerebro"
        if especs is None:
            especs, origen = respaldo, "heuristica"
        elif crudo == respaldo_json:
            origen = "heuristica"

        ya_respondidas = {p.id for p in respondidas}
        preguntas = preguntas_por_ambiguedad(pedido, tablas) + _preguntas_desde_json(datos)
        unicas: dict[str, Pregunta] = {}
        for p in preguntas:
            if p.id not in ya_respondidas:
                unicas.setdefault(p.id, p)
        return especs, list(unicas.values()), origen
