"""Casos de uso. Reciben sus puertos por constructor y no saben nada de HTTP,
SQL ni subprocesos.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from .errores import ItemNoEncontrado
from .modelos import Item, Lado, TareaBacklog
from .puertos import Cerebro, RepositorioBacklog, RepositorioItems

Alcance = Literal["BE", "FE", "todo"]


class ServicioItems:
    def __init__(self, repositorio: RepositorioItems) -> None:
        self._repo = repositorio

    async def listar(self) -> list[Item]:
        return await self._repo.listar()

    async def crear(self, name: str) -> Item:
        return await self._repo.crear(name)

    async def obtener(self, item_id: int) -> Item:
        item = await self._repo.obtener(item_id)
        if item is None:
            raise ItemNoEncontrado(item_id)
        return item

    async def actualizar(self, item_id: int, name: str) -> Item:
        item = await self._repo.actualizar(item_id, name)
        if item is None:
            raise ItemNoEncontrado(item_id)
        return item

    async def eliminar(self, item_id: int) -> None:
        borrado = await self._repo.eliminar(item_id)
        if not borrado:
            raise ItemNoEncontrado(item_id)


class ServicioBacklog:
    def __init__(self, repositorio: RepositorioBacklog, cerebro: Cerebro | None = None) -> None:
        self._repo = repositorio
        self._cerebro = cerebro

    def listar(self) -> list[TareaBacklog]:
        return self._repo.listar()

    def agregar(self, titulo: str, cuerpo: str, lado: Lado) -> TareaBacklog:
        tarea = TareaBacklog(id=self._siguiente_id(lado), titulo=titulo, cuerpo=cuerpo, lado=lado)
        self._repo.agregar(tarea)
        return tarea

    async def generar_desde_especificacion(
        self, texto: str, alcance: Alcance
    ) -> list[TareaBacklog]:
        """Convierte el texto de una especificación en tareas nuevas, ya
        agregadas a docs/BACKLOG.md.

        El "respaldo" que recibe el cerebro no es un texto fijo: es la misma
        división heurística por encabezados que se usa si no hay cerebro real
        (o si falla) — así el cerebro guionado (sin red) también produce algo
        útil, en vez de repetir siempre el mismo texto de ejemplo.
        """
        esbozos_heuristicos = _dividir_heuristicamente(texto, alcance)
        crudo = _serializar(esbozos_heuristicos)
        if self._cerebro is not None:
            crudo = await self._cerebro.pensar(
                _instruccion(alcance), contexto=texto[:12000], respaldo=crudo
            )

        esbozos = _parsear_tareas(crudo) or esbozos_heuristicos
        return [self.agregar(e.titulo, e.cuerpo, e.lado) for e in esbozos]

    def _siguiente_id(self, lado: Lado) -> str:
        numeros = [
            int(t.id.split("-", 1)[1])
            for t in self._repo.listar()
            if t.lado == lado and "-" in t.id and t.id.split("-", 1)[1].isdigit()
        ]
        return f"{lado}-{max(numeros, default=0) + 1:02d}"


@dataclass(frozen=True)
class _EsbozoTarea:
    titulo: str
    cuerpo: str
    lado: Lado


_MAX_TAREAS = 15

_PATRON_ENCABEZADO_MD = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
_PATRON_LISTA_NUMERADA = re.compile(r"^\s*\d+[.)]\s+(.+)$", re.MULTILINE)

_PALABRAS_BACKEND = (
    "api",
    "endpoint",
    "backend",
    "servidor",
    "base de datos",
    "modelo de datos",
    "autenticaci",
    "sqlalchemy",
    "fastapi",
    "persist",
    "esquema",
)
_PALABRAS_FRONTEND = (
    "ui",
    "interfaz",
    "pantalla",
    "componente",
    "botón",
    "formulario",
    "frontend",
    "página",
    "diseño",
    "react",
    "usuario final",
)


def _instruccion(alcance: Alcance) -> str:
    restriccion = {
        "BE": 'Todas las tareas son de backend: usá "lado": "BE" en cada una.',
        "FE": 'Todas las tareas son de frontend: usá "lado": "FE" en cada una.',
        "todo": (
            'Cada tarea es de backend ("BE") o de frontend ("FE") según a qué '
            "lado pertenezca — generá de ambos lados si el documento lo amerita."
        ),
    }[alcance]
    return (
        "Sos un tech lead dividiendo una especificación funcional/técnica en tareas de "
        "backlog concretas y accionables para un equipo de agentes de IA. Leé la "
        "especificación completa en el contexto: identificá cada requerimiento, pantalla, "
        "endpoint o regla de negocio distinta que describe, y convertí cada uno en su "
        "propia tarea. NUNCA devuelvas una sola tarea que resuma todo el documento — si "
        "el documento describe 5 funcionalidades, la respuesta tiene 5 tareas (o más, una "
        "por sub-tarea técnica si una funcionalidad requiere varios pasos claramente "
        "separables). Devolvé ENTRE 3 Y 15 tareas en total; si el documento da para menos "
        "de 3 tareas reales, dividí igual por aspecto técnico (ej. modelo de datos, "
        "endpoint, validaciones) en vez de agrupar todo. "
        f"{restriccion} Cada tarea tiene un título corto (menos de 100 caracteres) y un "
        "cuerpo en markdown con esta forma: 1-3 líneas describiendo qué hay que hacer, "
        "seguidas de '**Archivos:** ...', '**Verificación:** ...' y '**Depende de:** ...' "
        "(usá 'nada' si no depende de otra tarea de esta misma lista, o referenciá la tarea "
        "de la que depende por su título). Devolvé ÚNICAMENTE un array JSON, sin cercas de "
        "markdown ni texto fuera del array, con esta forma exacta: "
        '[{"lado": "BE"|"FE", "titulo": "...", "cuerpo": "..."}]'
    )


def _parsear_tareas(crudo: str) -> list[_EsbozoTarea] | None:
    texto = crudo.strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-zA-Z]*\n?|```\s*$", "", texto).strip()
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, list) or not datos:
        return None

    esbozos: list[_EsbozoTarea] = []
    for item in datos:
        if not isinstance(item, dict):
            continue
        lado = item.get("lado")
        titulo = str(item.get("titulo", "")).strip()
        cuerpo = str(item.get("cuerpo", "")).strip()
        if lado not in ("BE", "FE") or not titulo or not cuerpo:
            continue
        esbozos.append(_EsbozoTarea(titulo=titulo[:140], cuerpo=cuerpo[:4000], lado=lado))
    return esbozos[:_MAX_TAREAS] or None


def _serializar(esbozos: list[_EsbozoTarea]) -> str:
    return json.dumps(
        [{"lado": e.lado, "titulo": e.titulo, "cuerpo": e.cuerpo} for e in esbozos],
        ensure_ascii=False,
    )


def _dividir_heuristicamente(texto: str, alcance: Alcance) -> list[_EsbozoTarea]:
    """División determinista sin IA, en tres niveles — cada uno se prueba solo
    si el anterior no encontró al menos 2 secciones: (1) encabezados de
    markdown (`#`/`##`/`###` — incluye los que reconstruye
    `extraccion_documentos._extraer_docx` a partir de los estilos "Heading N"
    de Word), (2) ítems de lista numerada, (3) párrafos separados por línea
    en blanco. Es la que usa el cerebro guionado (sin conexión configurada) y
    el respaldo si el cerebro real falla — más tosca que una lectura real,
    pero siempre reparte el documento en varias tareas revisables en vez de
    devolver todo el texto como una sola.
    """
    secciones = _partir_en_secciones(texto)[:_MAX_TAREAS]
    if not secciones:
        secciones = [("Especificación importada", texto)]

    esbozos = []
    for titulo, cuerpo_bruto in secciones:
        lado = _lado_para(alcance, f"{titulo} {cuerpo_bruto}")
        resumen = cuerpo_bruto.strip()[:1500] or "(sin contenido debajo de este encabezado)"
        cuerpo = (
            f"{resumen}\n\n"
            "**Archivos:** por definir — tarea generada automáticamente a partir de un "
            "documento importado, sin revisión de un modelo de lenguaje real (no hay una "
            "conexión con Anthropic activa; ver Configuración). Revisar antes de asignar.\n\n"
            "**Verificación:** por definir.\n\n"
            "**Depende de:** nada."
        )
        esbozos.append(_EsbozoTarea(titulo=titulo[:140], cuerpo=cuerpo[:4000], lado=lado))
    return esbozos


def _partir_en_secciones(texto: str) -> list[tuple[str, str]]:
    secciones = _partir_por_posiciones(texto, _PATRON_ENCABEZADO_MD)
    if len(secciones) >= 2:
        return secciones

    secciones = _partir_por_posiciones(texto, _PATRON_LISTA_NUMERADA)
    if len(secciones) >= 2:
        return secciones

    return _partir_por_parrafos(texto)


def _partir_por_posiciones(texto: str, patron: re.Pattern[str]) -> list[tuple[str, str]]:
    posiciones = [(m.start(), m.group(1).strip()) for m in patron.finditer(texto)]
    if len(posiciones) < 2:
        return []

    secciones: list[tuple[str, str]] = []
    for i, (inicio, titulo) in enumerate(posiciones):
        fin = posiciones[i + 1][0] if i + 1 < len(posiciones) else len(texto)
        cuerpo = "\n".join(texto[inicio:fin].splitlines()[1:]).strip()
        secciones.append((titulo, cuerpo))
    return secciones


def _partir_por_parrafos(texto: str) -> list[tuple[str, str]]:
    """Último nivel: sin ningún encabezado ni lista reconocible (típico de un
    PDF cuyo texto extraído perdió todo el formato), al menos separar por
    párrafos (línea en blanco) en vez de tratar el documento entero como una
    sola tarea. El título de cada una sale de su primera oración.
    """
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if len(p.strip()) >= 40]
    if len(parrafos) < 2:
        return []

    secciones = []
    for parrafo in parrafos:
        primera_linea = parrafo.splitlines()[0].strip()
        titulo = re.split(r"(?<=[.!?])\s", primera_linea, maxsplit=1)[0][:90]
        secciones.append((titulo or "Sección de la especificación", parrafo))
    return secciones


def _lado_para(alcance: Alcance, texto: str) -> Lado:
    if alcance != "todo":
        return alcance
    texto_low = texto.lower()
    puntos_be = sum(texto_low.count(p) for p in _PALABRAS_BACKEND)
    puntos_fe = sum(texto_low.count(p) for p in _PALABRAS_FRONTEND)
    return "FE" if puntos_fe > puntos_be else "BE"
