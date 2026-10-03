"""Diseño guiado por especificaciones: de una lista suelta de requisitos a un
pedido completo para la fábrica.

La persona escribe requisitos uno por uno; mientras escribe, el sistema
reconoce de qué va el proyecto (la intención) y le ofrece cómo completar la
idea. Cuando dice "listo", se agrupan en módulos, se mide la cobertura por
categoría y, si falta algo, se pregunta o se recomienda cómo completarlo.

Las ideas vienen de dos herramientas de desarrollo guiado por
especificaciones:
- spec-kit (github/spec-kit, comando /clarify): revisar la especificación con
  una taxonomía de categorías (clara / parcial / falta), hacer como máximo 5
  preguntas de opción múltiple, cada una con una opción recomendada y el
  porqué, y dejar cada respuesta registrada como "pregunta → respuesta";
- Kiro: requisitos en notación EARS ("CUANDO …, EL SISTEMA DEBE …").

Todo lo de acá es determinista y puro: funciona sin LLM (cerebro guionado) y
es el respaldo cuando el Analista (agents/fabrica/analista.py) no responde.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_PREGUNTAS = 5
MAX_MODULOS = 6
MAX_PEDIDO = 8000

# --- vocabulario ---


def normal(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", base.lower()).strip()


_VACIAS = frozenset(
    "el la los las un una unos unas de del al y o en con por para que se su sus a "
    "es son como mas pero sin sobre entre cada todo toda todos todas este esta "
    "debe deben poder puede quiero quiere necesito sistema".split()
)


def _raiz(palabra: str) -> str:
    """Singular aproximado: "productos" y "producto" cuentan igual. El "-es"
    se quita solo tras consonante ("cupones" → "cupon"), no en "clientes".
    """
    if len(palabra) > 4 and palabra.endswith("es") and palabra[-3] in "lnrdzjy":
        return palabra[:-2]
    if len(palabra) > 3 and palabra.endswith("s"):
        return palabra[:-1]
    return palabra


def terminos(texto: str) -> set[str]:
    return {
        _raiz(p) for p in re.findall(r"[a-z0-9]+", normal(texto)) if len(p) > 2 and p not in _VACIAS
    }


def similitud(a: str, b: str) -> float:
    ta, tb = terminos(a), terminos(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# --- catálogos ---


@dataclass(frozen=True)
class Dominio:
    clave: str
    nombre: str
    palabras: tuple[str, ...]
    entidades: tuple[str, ...]
    sugerencias: tuple[str, ...]


DOMINIOS: tuple[Dominio, ...] = (
    Dominio(
        "tienda",
        "Tienda en línea",
        (
            "producto",
            "carrito",
            "compra",
            "venta",
            "pedido",
            "checkout",
            "catalogo",
            "precio",
            "stock",
            "cupon",
            "envio",
            "tienda",
        ),
        ("producto", "carrito", "pedido", "cupon", "cliente", "pago"),
        (
            "Registrar productos con nombre, precio, stock y foto",
            "Agregar productos al carrito y calcular el total con impuestos",
            "Aplicar cupones de descuento sobre el total del carrito",
            "Confirmar un pedido y descontar del stock lo vendido",
            "Consultar el historial de pedidos de un cliente",
        ),
    ),  # fmt: skip
    Dominio(
        "encuestas",
        "Encuestas y formularios",
        (
            "encuesta",
            "pregunta",
            "respuesta",
            "formulario",
            "votacion",
            "voto",
            "opinion",
            "cuestionario",
        ),
        ("encuesta", "pregunta", "respuesta"),
        (
            "Crear encuestas con preguntas de opción múltiple y abiertas",
            "Responder una encuesta una sola vez por persona",
            "Ver los resultados de una encuesta con el porcentaje de cada opción",
            "Cerrar una encuesta automáticamente en su fecha límite",
            "Exportar las respuestas de una encuesta a CSV",
        ),
    ),  # fmt: skip
    Dominio(
        "crm",
        "Gestión de clientes (CRM)",
        (
            "lead",
            "prospecto",
            "contacto",
            "seguimiento",
            "oportunidad",
            "embudo",
            "crm",
            "cliente",
            "vendedor",
        ),
        ("lead", "cliente", "contacto", "oportunidad", "vendedor"),
        (
            "Registrar leads con nombre, email, teléfono y origen",
            "Mover un lead por las etapas del embudo de ventas",
            "Registrar notas de seguimiento en cada cliente",
            "Asignar cada lead a un vendedor responsable",
            "Ver cuántos leads hay en cada etapa del embudo",
        ),
    ),  # fmt: skip
    Dominio(
        "reservas",
        "Reservas y turnos",
        (
            "reserva",
            "turno",
            "cita",
            "agenda",
            "horario",
            "disponibilidad",
            "calendario",
            "sala",
            "cancha",
        ),
        ("reserva", "turno", "horario", "sala"),
        (
            "Ver los horarios disponibles de cada día",
            "Reservar un turno en un horario libre",
            "Impedir dos reservas en el mismo horario",
            "Cancelar una reserva hasta 24 horas antes",
            "Enviar un recordatorio antes de cada turno",
        ),
    ),  # fmt: skip
    Dominio(
        "inventario",
        "Inventario y almacén",
        (
            "inventario",
            "stock",
            "almacen",
            "bodega",
            "existencia",
            "proveedor",
            "entrada",
            "salida",
            "lote",
            "sku",
        ),
        ("articulo", "proveedor", "movimiento", "almacen"),
        (
            "Registrar artículos con código, descripción y stock mínimo",
            "Registrar entradas y salidas de stock con fecha y motivo",
            "Avisar cuando un artículo baja de su stock mínimo",
            "Registrar proveedores y asociarlos a sus artículos",
            "Generar un reporte de existencias valorizado",
        ),
    ),  # fmt: skip
    Dominio(
        "finanzas",
        "Finanzas y facturación",
        (
            "factura",
            "gasto",
            "ingreso",
            "presupuesto",
            "cobro",
            "impuesto",
            "contabilidad",
            "finanza",
            "saldo",
            "balance",
        ),
        ("factura", "gasto", "ingreso", "pago", "cuenta"),
        (
            "Registrar gastos e ingresos con categoría y fecha",
            "Emitir facturas con el detalle de ítems e impuestos",
            "Registrar pagos parciales de una factura y calcular el saldo",
            "Ver el balance mensual por categoría",
            "Marcar las facturas vencidas sin pagar",
        ),
    ),  # fmt: skip
    Dominio(
        "tareas",
        "Tareas y proyectos",
        (
            "tarea",
            "proyecto",
            "pendiente",
            "equipo",
            "responsable",
            "plazo",
            "sprint",
            "kanban",
            "prioridad",
        ),
        ("tarea", "proyecto", "comentario"),
        (
            "Crear tareas con título, responsable, prioridad y fecha límite",
            "Mover tareas entre pendiente, en curso y terminada",
            "Agrupar las tareas por proyecto",
            "Listar las tareas vencidas de cada responsable",
            "Comentar dentro de una tarea",
        ),
    ),  # fmt: skip
    Dominio(
        "educacion",
        "Cursos y educación",
        (
            "curso",
            "alumno",
            "estudiante",
            "clase",
            "leccion",
            "profesor",
            "calificacion",
            "examen",
            "inscripcion",
        ),
        ("curso", "alumno", "leccion", "calificacion"),
        (
            "Registrar cursos con sus lecciones en orden",
            "Inscribir alumnos en un curso",
            "Registrar calificaciones y calcular el promedio de cada alumno",
            "Marcar lecciones completadas y mostrar el avance del alumno",
            "Emitir un certificado al completar un curso",
        ),
    ),  # fmt: skip
)


@dataclass(frozen=True)
class Categoria:
    """Una dimensión de la taxonomía de cobertura (adaptada de spec-kit)."""

    clave: str
    nombre: str
    palabras: tuple[str, ...]
    pregunta: str
    porque: str
    opciones: tuple[str, ...]
    recomendada: int
    # Requisito para completar el hueco; {entidad} = la entidad principal.
    requisito: str
    impacto: int


CATEGORIAS: tuple[Categoria, ...] = (
    Categoria(
        "usuarios",
        "Usuarios y alcance",
        (
            "usuario",
            "administrador",
            "admin",
            "rol",
            "persona",
            "vendedor",
            "alumno",
            "publico",
            "cliente",
            "equipo",
        ),
        "¿Quién va a usar el sistema?",
        "Define qué pantallas hacen falta y qué puede ver o cambiar cada persona.",
        (
            "Usuarios registrados y un administrador",
            "Una sola persona (uso interno)",
            "Público general, sin registro",
        ),
        0,
        "Distinguir entre administradores y usuarios, con permisos distintos sobre {entidad}",
        5,
    ),  # fmt: skip
    Categoria(
        "datos",
        "Datos y entidades",
        (
            "registrar",
            "guardar",
            "nombre",
            "email",
            "fecha",
            "campo",
            "dato",
            "codigo",
            "precio",
            "telefono",
            "descripcion",
        ),
        "¿Qué datos hay que guardar de cada elemento principal?",
        "Sin esto el modelo de datos se adivina, y cambiarlo después cuesta más.",
        (
            "Datos completos con validaciones",
            "Solo lo esencial (nombre y fecha)",
            "Lo detallo en cada requisito",
        ),
        0,
        "Validar que los campos obligatorios de {entidad} estén completos y bien formados",
        5,
    ),  # fmt: skip
    Categoria(
        "reglas",
        "Reglas y cálculos",
        (
            "calcular",
            "total",
            "validar",
            "regla",
            "impuesto",
            "descuento",
            "limite",
            "maximo",
            "minimo",
            "impedir",
            "solo",
            "promedio",
            "saldo",
        ),
        "¿Hay reglas de negocio o cálculos que el sistema deba aplicar?",
        "Las reglas son lo que más se rompe si no se escriben: cada una se vuelve una prueba.",
        (
            "Validar datos obligatorios y formatos",
            "Además, cálculos con totales e impuestos",
            "Sin reglas especiales",
        ),
        0,
        "Rechazar valores imposibles en {entidad} (cantidades negativas, fechas inválidas)",
        4,
    ),  # fmt: skip
    Categoria(
        "interfaz",
        "Interfaz",
        (
            "pantalla",
            "formulario",
            "pagina",
            "boton",
            "vista",
            "panel",
            "tablero",
            "interfaz",
            "listado",
            "mostrar",
            "ver",
            "web",
        ),
        "¿Cómo se va a usar el sistema?",
        "Decide si se construyen pantallas o solo una API, y si hay pruebas de interfaz.",
        (
            "Pantallas web con formularios y listados",
            "Solo una API, sin interfaz",
            "Pantallas web y API",
        ),
        0,
        "Mostrar un listado de {entidad} con búsqueda y un formulario para crear y editar",
        4,
    ),  # fmt: skip
    Categoria(
        "errores",
        "Errores y casos borde",
        (
            "error",
            "invalido",
            "vacio",
            "duplicado",
            "existe",
            "falla",
            "mensaje",
            "rechazar",
            "avisar",
            "alerta",
        ),
        "¿Qué hace el sistema ante datos inválidos o duplicados?",
        "Los casos borde son donde más fallan las implementaciones generadas.",
        (
            "Rechazarlos con un mensaje claro",
            "Guardarlos marcados para revisión",
            "Ignorarlos en silencio",
        ),
        0,
        "CUANDO se intente guardar un registro de {entidad} duplicado o incompleto, EL "
        "SISTEMA DEBE rechazarlo con un mensaje que explique qué corregir",
        3,
    ),  # fmt: skip
    Categoria(
        "seguridad",
        "Seguridad y permisos",
        (
            "login",
            "sesion",
            "contrasena",
            "password",
            "permiso",
            "autenticar",
            "acceso",
            "privado",
            "seguridad",
        ),
        "¿Hace falta iniciar sesión?",
        "Cambia la arquitectura: sin esto, cualquiera con el enlace puede modificar datos.",
        ("Sí, con usuario y contraseña", "No, es de uso interno", "Solo para administrar"),
        0,
        "CUANDO una persona no haya iniciado sesión, EL SISTEMA DEBE impedirle modificar {entidad}",
        3,
    ),  # fmt: skip
    Categoria(
        "aceptacion",
        "Criterios de aceptación",
        ("cuando", "entonces", "criterio", "aceptacion", "prueba", "verificar", "exito"),
        "¿Cómo sabremos que está terminado?",
        "La fábrica solo aprueba lo que una prueba demuestra.",
        (
            "Cada requisito con una prueba automática que lo demuestra",
            "Una revisión manual alcanza",
            "Lo defino después",
        ),
        0,
        "Cada requisito tiene al menos una prueba automática que demuestra que se cumple",
        2,
    ),  # fmt: skip
)

_CATEGORIA = {c.clave: c for c in CATEGORIAS}
_ETIQUETA_ENTIDAD = {
    "cupon": "Cupones", "leccion": "Lecciones", "calificacion": "Calificaciones",
    "articulo": "Artículos", "almacen": "Almacenes", "inscripcion": "Inscripciones",
}  # fmt: skip


def etiqueta_entidad(entidad: str) -> str:
    if entidad in _ETIQUETA_ENTIDAD:
        return _ETIQUETA_ENTIDAD[entidad]
    return entidad.capitalize() + ("s" if entidad[-1] in "aeiou" else "es")


# --- resultados ---


@dataclass(frozen=True)
class Intencion:
    dominio: str | None
    nombre: str
    resumen: str
    confianza: float
    entidades: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Modulo:
    nombre: str
    # Posiciones en la lista de requisitos: un módulo nunca reescribe ni
    # pierde lo que escribió la persona.
    requisitos: list[int]


@dataclass(frozen=True)
class PreguntaRequisito:
    id: str
    categoria: str
    texto: str
    porque: str
    opciones: list[str]
    recomendada: int


@dataclass(frozen=True)
class Recomendacion:
    texto: str
    categoria: str
    porque: str


@dataclass(frozen=True)
class RespuestaRequisito:
    categoria: str
    pregunta: str
    respuesta: str


@dataclass(frozen=True)
class Sugerencias:
    intencion: Intencion
    autocompletado: list[str]
    sugerencias: list[str]


@dataclass(frozen=True)
class AnalisisRequisitos:
    intencion: Intencion
    modulos: list[Modulo]
    # categoría → "clara" | "parcial" | "falta" | "resuelta"
    cobertura: dict[str, str]
    preguntas: list[PreguntaRequisito]
    recomendaciones: list[Recomendacion]
    listo: bool
    origen: str = "heuristica"


# --- intención ---


def detectar_intencion(textos: list[str]) -> Intencion:
    vocab = terminos(" ".join(textos))
    puntajes = [(len(vocab & {_raiz(p) for p in d.palabras}), d) for d in DOMINIOS]
    puntaje, dominio = max(puntajes, key=lambda x: x[0])
    if puntaje == 0:
        return Intencion(
            None,
            "Sistema a medida",
            "Todavía no reconozco el tipo de proyecto: sigue describiendo qué tiene que hacer.",
            0.0,
            entidades_de(textos),
        )
    entidades = [e for e in dominio.entidades if _raiz(e) in vocab] or list(dominio.entidades[:2])
    nombres = [etiqueta_entidad(e).lower() for e in entidades[:3]]
    lista = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
    return Intencion(
        dominio.clave,
        dominio.nombre,
        f"Parece un sistema de {dominio.nombre.lower()} centrado en {lista}.",
        round(puntaje / (puntaje + 2), 2),
        entidades,
    )


def entidades_de(textos: list[str]) -> list[str]:
    """Entidades conocidas que aparecen en el texto, en orden de aparición."""
    conocidas = {_raiz(e): e for d in DOMINIOS for e in d.entidades}
    vistas: list[str] = []
    for texto in textos:
        for p in re.findall(r"[a-z0-9]+", normal(texto)):
            e = conocidas.get(_raiz(p))
            if e and e not in vistas:
                vistas.append(e)
    return vistas


def _dominio(clave: str | None) -> Dominio | None:
    return next((d for d in DOMINIOS if d.clave == clave), None)


def _cubierto(texto: str, requisitos: list[str], umbral: float = 0.45) -> bool:
    return any(similitud(texto, r) >= umbral for r in requisitos)


# --- sugerencias en vivo ---


def sugerir(requisitos: list[str], borrador: str = "") -> Sugerencias:
    """Mientras se escribe: de qué va el proyecto, cómo completar la frase
    que se está escribiendo y qué requisitos típicos faltan.
    """
    requisitos = [r for r in requisitos if r.strip()]
    intencion = detectar_intencion([*requisitos, borrador])
    dominio = _dominio(intencion.dominio)
    candidatos = (
        list(dominio.sugerencias) if dominio else [s for d in DOMINIOS for s in d.sugerencias]
    )

    autocompletado: list[str] = []
    b = normal(borrador)
    if len(b) >= 3:
        puntuados = []
        for c in candidatos:
            if _cubierto(c, requisitos):
                continue
            n = normal(c)
            prefijo = 1.0 if n.startswith(b) else 0.0
            comun = len(terminos(b) & terminos(c))
            if prefijo or comun:
                puntuados.append((prefijo + comun, c))
        puntuados.sort(key=lambda x: -x[0])
        autocompletado = [c for _, c in puntuados[:3]]

    sugerencias = (
        [s for s in dominio.sugerencias if not _cubierto(s, requisitos) and s not in autocompletado]
        if dominio
        else []
    )
    return Sugerencias(intencion, autocompletado, sugerencias[:4])


# --- análisis al terminar ---


def agrupar(requisitos: list[str]) -> list[Modulo]:
    """Un módulo por entidad principal de cada requisito; lo que no menciona
    ninguna va a "General". Como mucho MAX_MODULOS: el Especificador parte en
    hasta 6 especificaciones y cada módulo se vuelve una.
    """
    grupos: dict[str, list[int]] = {}
    for i, r in enumerate(requisitos):
        entidades = entidades_de([r])
        nombre = etiqueta_entidad(entidades[0]) if entidades else "General"
        grupos.setdefault(nombre, []).append(i)
    modulos = [Modulo(n, idx) for n, idx in grupos.items()]
    while len(modulos) > MAX_MODULOS:
        modulos.sort(key=lambda m: len(m.requisitos))
        chico, otro = modulos[0], modulos[1]
        destino = next((m for m in modulos if m.nombre == "General"), None)
        if destino is None or destino is chico:
            destino = otro
        fusion = Modulo(destino.nombre, sorted(destino.requisitos + chico.requisitos))
        modulos = [m for m in modulos if m is not chico and m is not destino] + [fusion]
    modulos.sort(key=lambda m: m.requisitos[0])
    return modulos


def cobertura(requisitos: list[str], respondidas: set[str]) -> dict[str, str]:
    vocab = terminos(" ".join(requisitos))
    resultado: dict[str, str] = {}
    for c in CATEGORIAS:
        if c.clave in respondidas:
            resultado[c.clave] = "resuelta"
            continue
        aciertos = len(vocab & {_raiz(p) for p in c.palabras})
        resultado[c.clave] = "clara" if aciertos >= 2 else "parcial" if aciertos else "falta"
    return resultado


def analizar(
    requisitos: list[str], respuestas: list[RespuestaRequisito] | None = None
) -> AnalisisRequisitos:
    requisitos = [r.strip() for r in requisitos if r.strip()]
    respuestas = respuestas or []
    respondidas = {r.categoria for r in respuestas}
    intencion = detectar_intencion(requisitos)
    estado = cobertura(requisitos, respondidas)

    pendientes = sorted(
        (c for c in CATEGORIAS if estado[c.clave] == "falta"), key=lambda c: -c.impacto
    )[:MAX_PREGUNTAS]
    preguntas = [
        PreguntaRequisito(c.clave, c.clave, c.pregunta, c.porque, list(c.opciones), c.recomendada)
        for c in pendientes
    ]

    entidad = (intencion.entidades or entidades_de(requisitos) or ["cada registro"])[0]
    textos_entidad = etiqueta_entidad(entidad).lower() if entidad != "cada registro" else entidad
    recomendaciones: list[Recomendacion] = []
    for c in CATEGORIAS:
        if estado[c.clave] in ("falta", "parcial"):
            texto = c.requisito.format(entidad=textos_entidad)
            if not _cubierto(texto, requisitos):
                recomendaciones.append(Recomendacion(texto, c.clave, c.porque))
    dominio = _dominio(intencion.dominio)
    if dominio:
        for s in dominio.sugerencias:
            if not _cubierto(s, requisitos) and len(recomendaciones) < 8:
                recomendaciones.append(
                    Recomendacion(s, "alcance", f"Es habitual en {dominio.nombre.lower()}.")
                )

    return AnalisisRequisitos(
        intencion=intencion,
        modulos=agrupar(requisitos),
        cobertura=estado,
        preguntas=preguntas,
        recomendaciones=recomendaciones,
        listo=bool(requisitos) and not preguntas,
    )


# --- composición del pedido ---


def a_ears(requisito: str) -> str:
    """Notación EARS (Kiro): "CUANDO …, EL SISTEMA DEBE …". Lo que ya viene en
    esa forma se respeta; el resto se vuelve una obligación del sistema.
    """
    texto = requisito.strip().rstrip(".")
    if re.match(r"^(cuando|si|mientras|donde|el sistema debe|cada)\b", normal(texto)):
        return texto
    minuscula = texto[:1].lower() + texto[1:]
    # "Registrar productos" → "EL SISTEMA DEBE registrar productos"; una frase
    # que no arranca con un infinitivo ("Los clientes ven sus pedidos") va con
    # "garantizar que" para que la oración siga siendo gramatical.
    if re.match(r"^[a-z]+(ar|er|ir)\b", normal(texto)):
        return "EL SISTEMA DEBE " + minuscula
    return "EL SISTEMA DEBE garantizar que " + minuscula


def componer_pedido(
    requisitos: list[str],
    respuestas: list[RespuestaRequisito] | None = None,
    modulos: list[Modulo] | None = None,
    resumen: str = "",
) -> str:
    """El pedido para la fábrica: contexto y decisiones arriba, y una viñeta
    por módulo — el Especificador convierte cada viñeta en una especificación
    (las independientes se construyen en paralelo).
    """
    requisitos = [r.strip() for r in requisitos if r.strip()]
    respuestas = respuestas or []
    modulos = modulos if modulos and modulos_validos(modulos, len(requisitos)) else None
    modulos = modulos or agrupar(requisitos)
    resumen = resumen or detectar_intencion(requisitos).resumen

    lineas = [f"Proyecto: {resumen}"]
    if respuestas:
        lineas.append(
            "Decisiones: " + "; ".join(f"{r.pregunta} → {r.respuesta}" for r in respuestas) + "."
        )
    lineas.append("")
    for m in modulos:
        cuerpo = "; ".join(a_ears(requisitos[i]) for i in m.requisitos)
        lineas.append(f"- Módulo {m.nombre}: {cuerpo}.")
    aceptacion = next((r for r in respuestas if r.categoria == "aceptacion"), None)
    if aceptacion is None or "prueba" in normal(aceptacion.respuesta):
        lineas.append("")
        lineas.append(
            "Criterio de aceptación: cada requisito tiene al menos una prueba automática "
            "que demuestra que se cumple."
        )
    pedido = "\n".join(lineas)
    return pedido if len(pedido) <= MAX_PEDIDO else pedido[: MAX_PEDIDO - 1] + "…"


def modulos_validos(modulos: list[Modulo], n_requisitos: int) -> bool:
    """Cada requisito en exactamente un módulo, sin índices inventados."""
    indices = [i for m in modulos for i in m.requisitos]
    return (
        0 < len(modulos) <= MAX_MODULOS
        and all(m.nombre.strip() and m.requisitos for m in modulos)
        and sorted(indices) == list(range(n_requisitos))
    )


def categoria(clave: str) -> Categoria | None:
    return _CATEGORIA.get(clave)
