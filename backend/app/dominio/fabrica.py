"""La fábrica de software: un encargo en lenguaje natural que el Líder lleva
de especificación a despliegue, pasando por implementación, revisión,
diagnóstico y verificación.

Todo lo que está acá es determinista y puro: entidades, el orden de las
dependencias, la política que acota a los agentes y el sellado de la
bitácora. La IA propone; estas reglas deciden qué se acepta. Así el resultado
se puede reproducir aunque el modelo no lo sea.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

EstadoEspec = Literal[
    "pendiente", "esperando_aprobacion", "en_curso", "aprobada", "fallida", "bloqueada"
]
EstadoEncargo = Literal[
    "especificando", "esperando_humano", "en_curso", "terminado", "fallido", "interrumpido"
]
Etapa = Literal[
    "especificacion", "implementacion", "revision", "diagnostico", "verificacion", "despliegue"
]
CausaFallo = Literal["especificacion", "harness", "implementacion"]
ModoAprobacion = Literal["nunca", "ambiguedad", "siempre"]
OrigenPregunta = Literal["especificador", "diagnosticador"]

ESTADOS_ACTIVOS: frozenset[str] = frozenset({"especificando", "en_curso"})
HASH_GENESIS = "0" * 64


def ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


# --- entidades ---


@dataclass
class Especificacion:
    """Una unidad pequeña y verificable de trabajo. `archivos` es el contrato:
    el Revisor rechaza si falta alguno, sin importar lo que diga el agente.
    """

    id: str
    titulo: str
    descripcion: str
    criterios: list[str] = field(default_factory=list)
    archivos: list[str] = field(default_factory=list)
    depende_de: list[str] = field(default_factory=list)
    requiere_aprobacion: bool = False
    e2e: bool = False
    estado: EstadoEspec = "pendiente"
    intentos: int = 0
    motivo: str = ""
    aprobada_por_humano: bool = False


@dataclass
class Pregunta:
    """Una ambigüedad que un agente no debe resolver solo — por ejemplo, un
    pedido que choca con una tabla legada. El pipeline se pausa hasta que una
    persona la responde.
    """

    id: str
    texto: str
    opciones: list[str] = field(default_factory=list)
    respuesta: str | None = None
    origen: OrigenPregunta = "especificador"
    espec_id: str | None = None
    # La solución concreta que sugirió el Diagnosticador, si la hubo: elegir
    # "Reintentar con la propuesta" se la pasa al Implementador como instrucción.
    propuesta: str | None = None


@dataclass
class Encargo:
    id: str
    pedido: str
    estado: EstadoEncargo = "especificando"
    especificaciones: list[Especificacion] = field(default_factory=list)
    preguntas: list[Pregunta] = field(default_factory=list)
    costo_usd: float = 0.0
    motivo: str = ""
    url_despliegue: str | None = None
    creado_en: str = field(default_factory=ahora_iso)
    actualizado_en: str = field(default_factory=ahora_iso)
    # Versionado: una iteración arranca con una copia de los archivos de otro
    # encargo (su padre). Todas las versiones de un mismo producto comparten
    # la raíz, que es el id de la v1.
    version: int = 1
    padre_id: str | None = None
    raiz_id: str | None = None
    # Reiniciar la línea no borra nada: archiva. Un encargo archivado sale de
    # la oficina pero sigue en Ejecuciones, con su bitácora intacta.
    archivado_en: str | None = None

    @property
    def linaje(self) -> str:
        return self.raiz_id or self.id

    def preguntas_abiertas(self) -> list[Pregunta]:
        return [p for p in self.preguntas if p.respuesta is None]

    def espec(self, espec_id: str) -> Especificacion | None:
        return next((e for e in self.especificaciones if e.id == espec_id), None)

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Ejecucion:
    """Una ejecución vista desde Ejecuciones: lo que dice la base (pedido,
    estado, versión) cruzado con lo que hay en disco (su carpeta en
    fabrica_espacios/). Puede faltar cualquiera de los dos: un encargo que
    falló al especificar no llegó a tener carpeta, y una carpeta puede
    venir de otra base de datos.
    """

    id: str
    en_base: bool
    carpeta: bool
    pedido: str | None = None
    estado: EstadoEncargo | None = None
    version: int = 1
    padre_id: str | None = None
    raiz_id: str | None = None
    archivado_en: str | None = None
    creado_en: str | None = None
    costo_usd: float = 0.0
    especificaciones: int = 0
    aprobadas: int = 0
    archivos: int = 0
    bytes: int = 0
    modificado_en: str | None = None


def encargo_desde_dict(datos: dict[str, Any]) -> Encargo:
    """Inversa de Encargo.a_dict(). Tolera claves nuevas o faltantes para que
    un encargo guardado por una versión anterior siga abriendo.
    """
    especs = [
        Especificacion(**_filtrar(Especificacion, e)) for e in datos.get("especificaciones", [])
    ]
    preguntas = [Pregunta(**_filtrar(Pregunta, p)) for p in datos.get("preguntas", [])]
    base = _filtrar(Encargo, datos)
    base.pop("especificaciones", None)
    base.pop("preguntas", None)
    return Encargo(**base, especificaciones=especs, preguntas=preguntas)


def _filtrar(clase: type, datos: dict[str, Any]) -> dict[str, Any]:
    campos = clase.__dataclass_fields__  # type: ignore[attr-defined]
    return {k: v for k, v in datos.items() if k in campos}


# --- consumo, métricas y bitácora ---


@dataclass(frozen=True)
class Consumo:
    """Lo que costó una llamada al cerebro. `costo_usd` es None cuando el
    modelo no tiene tarifa conocida: mejor un hueco explícito que un número
    inventado.
    """

    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float | None = 0.0


@dataclass(frozen=True)
class RespuestaMedida:
    texto: str
    consumo: Consumo


@dataclass(frozen=True)
class MetricaEtapa:
    """Cuánto costó y cuánto tardó una etapa. Con esto se arma la velocidad
    histórica de la fábrica — el dato que con un equipo humano es tan variable.
    """

    encargo_id: str
    etapa: Etapa
    agente: str
    resultado: str
    duracion_s: float
    espec_id: str | None = None
    intento: int = 1
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float | None = 0.0
    ts: str = field(default_factory=ahora_iso)


@dataclass(frozen=True)
class RegistroBitacora:
    """Una entrada sellada. `evidencia` es lo que el harness midió (hashes de
    archivos en disco, código de salida de un comando), no lo que el agente
    dijo que hizo. Cada registro incluye el hash del anterior: cambiar uno
    rompe la cadena desde ahí en adelante.
    """

    secuencia: int
    encargo_id: str
    agente: str
    accion: str
    evidencia: dict[str, Any]
    ts: str
    hash_previo: str
    hash: str


def _contenido_sellado(
    secuencia: int,
    encargo_id: str,
    agente: str,
    accion: str,
    evidencia: dict[str, Any],
    ts: str,
    hash_previo: str,
) -> str:
    return json.dumps(
        {
            "secuencia": secuencia,
            "encargo_id": encargo_id,
            "agente": agente,
            "accion": accion,
            "evidencia": evidencia,
            "ts": ts,
            "hash_previo": hash_previo,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def sellar(
    secuencia: int,
    encargo_id: str,
    agente: str,
    accion: str,
    evidencia: dict[str, Any],
    hash_previo: str,
    ts: str | None = None,
) -> RegistroBitacora:
    momento = ts or ahora_iso()
    contenido = _contenido_sellado(
        secuencia, encargo_id, agente, accion, evidencia, momento, hash_previo
    )
    return RegistroBitacora(
        secuencia=secuencia,
        encargo_id=encargo_id,
        agente=agente,
        accion=accion,
        evidencia=evidencia,
        ts=momento,
        hash_previo=hash_previo,
        hash=hashlib.sha256(contenido.encode("utf-8")).hexdigest(),
    )


def primer_registro_roto(registros: list[RegistroBitacora]) -> int | None:
    """Recorre la cadena completa (en orden de secuencia) y devuelve la
    secuencia del primer registro alterado, o None si está íntegra.
    """
    previo = HASH_GENESIS
    for r in sorted(registros, key=lambda r: r.secuencia):
        esperado = sellar(
            r.secuencia, r.encargo_id, r.agente, r.accion, r.evidencia, previo, r.ts
        ).hash
        if r.hash_previo != previo or r.hash != esperado:
            return r.secuencia
        previo = r.hash
    return None


def sha256_texto(contenido: str) -> str:
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


# --- veredictos ---


@dataclass(frozen=True)
class Veredicto:
    aprobado: bool
    motivo: str = ""
    evidencia: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Diagnostico:
    causa: CausaFallo
    explicacion: str


@dataclass(frozen=True)
class ResultadoComando:
    comando: list[str]
    codigo_salida: int
    salida: str
    duracion_s: float
    sandbox: str


# --- política: los límites que hacen reproducible al pipeline ---


@dataclass(frozen=True)
class PoliticaFabrica:
    max_intentos: int = 2
    # 0 desactiva el tope.
    presupuesto_encargo_usd: float = 1.0
    aprobacion_humana: ModoAprobacion = "ambiguedad"
    directorios_escritura: tuple[str, ...] = ("src/", "tests/", "frontend/", "e2e/")


def ruta_permitida(ruta: str, politica: PoliticaFabrica) -> bool:
    """Un agente escribe solo dentro de los directorios permitidos del espacio
    de trabajo: nada absoluto, nada que suba con `..`, nunca un `.env`.
    """
    normal = ruta.replace("\\", "/").strip()
    if not normal or normal.startswith("/") or ":" in normal:
        return False
    partes = normal.split("/")
    if any(p in ("", ".", "..") for p in partes):
        return False
    if partes[-1].startswith(".env"):
        return False
    return any(normal.startswith(d) for d in politica.directorios_escritura)


def presupuesto_agotado(encargo: Encargo, politica: PoliticaFabrica) -> bool:
    return 0 < politica.presupuesto_encargo_usd <= encargo.costo_usd


def aplicar_modo_aprobacion(encargo: Encargo, modo: ModoAprobacion) -> list[str]:
    """Ajusta las compuertas humanas según la política. Con "nunca", cada
    pregunta abierta se resuelve con su primera opción y se devuelve la lista
    de decisiones tomadas para dejarlas en la bitácora — la fábrica decide,
    pero no a escondidas.
    """
    decisiones: list[str] = []
    if modo == "siempre":
        for e in encargo.especificaciones:
            e.requiere_aprobacion = True
    elif modo == "nunca":
        for e in encargo.especificaciones:
            e.requiere_aprobacion = False
        for p in encargo.preguntas_abiertas():
            p.respuesta = p.opciones[0] if p.opciones else "Seguir con el criterio por defecto"
            decisiones.append(f"{p.texto} → {p.respuesta}")
    return decisiones


# --- dependencias ---


def orden_topologico(especs: list[Especificacion]) -> tuple[list[str], list[str]]:
    """Kahn. Devuelve (orden, ids_en_ciclo). Estable: a igual nivel, el orden
    en que el Especificador las escribió.
    """
    ids = [e.id for e in especs]
    conocidos = set(ids)
    grado = {i: 0 for i in ids}
    dependientes: dict[str, list[str]] = {i: [] for i in ids}
    for e in especs:
        for d in e.depende_de:
            if d in conocidos and d != e.id:
                grado[e.id] += 1
                dependientes[d].append(e.id)

    cola = deque(i for i in ids if grado[i] == 0)
    orden: list[str] = []
    while cola:
        actual = cola.popleft()
        orden.append(actual)
        for dep in dependientes[actual]:
            grado[dep] -= 1
            if grado[dep] == 0:
                cola.append(dep)
    return orden, [i for i in ids if grado[i] > 0]


def validar_dependencias(especs: list[Especificacion]) -> list[str]:
    errores: list[str] = []
    ids = [e.id for e in especs]
    if len(set(ids)) != len(ids):
        errores.append("Hay especificaciones con el mismo id")
    conocidos = set(ids)
    for e in especs:
        for d in e.depende_de:
            if d == e.id:
                errores.append(f"{e.id} depende de sí misma")
            elif d not in conocidos:
                errores.append(f"{e.id} depende de {d}, que no existe")
    _, ciclo = orden_topologico(especs)
    if ciclo:
        errores.append(f"Dependencia circular entre {', '.join(sorted(ciclo))}")
    return errores


def especificaciones_listas(encargo: Encargo) -> list[Especificacion]:
    """Todas las que pueden correr ya — sus dependencias están aprobadas —, en
    orden topológico. Son independientes entre sí por construcción: si una
    dependiera de otra de la lista, esa otra no estaría aprobada todavía. Por
    eso el Líder las puede correr en paralelo.

    Efecto lateral a propósito: una pendiente cuya dependencia falló queda
    "bloqueada" — si no, el Líder esperaría para siempre algo que no va a llegar.
    """
    orden, _ = orden_topologico(encargo.especificaciones)
    por_id = {e.id: e for e in encargo.especificaciones}
    listas: list[Especificacion] = []
    for espec_id in orden:
        e = por_id[espec_id]
        if e.estado not in ("pendiente", "esperando_aprobacion", "en_curso"):
            continue
        estados_deps = [por_id[d].estado for d in e.depende_de if d in por_id]
        if any(s in ("fallida", "bloqueada") for s in estados_deps):
            e.estado = "bloqueada"
            e.motivo = "Una especificación de la que depende no se aprobó"
            continue
        if all(s == "aprobada" for s in estados_deps):
            listas.append(e)
    return listas


def siguiente_especificacion(encargo: Encargo) -> Especificacion | None:
    listas = especificaciones_listas(encargo)
    return listas[0] if listas else None


def niveles(especs: list[Especificacion]) -> dict[str, int]:
    """Profundidad de cada especificación en el grafo (1 = sin dependencias).
    Las de un mismo nivel pueden correr en paralelo.
    """
    orden, _ = orden_topologico(especs)
    por_id = {e.id: e for e in especs}
    nivel: dict[str, int] = {}
    for espec_id in orden:
        deps = [d for d in por_id[espec_id].depende_de if d in nivel]
        nivel[espec_id] = 1 + max((nivel[d] for d in deps), default=0)
    return nivel


def estado_final(encargo: Encargo) -> Literal["terminado", "fallido"] | None:
    """None si todavía queda algo por hacer."""
    estados = [e.estado for e in encargo.especificaciones]
    if any(s in ("pendiente", "esperando_aprobacion", "en_curso") for s in estados):
        return None
    return "terminado" if estados and all(s == "aprobada" for s in estados) else "fallido"
