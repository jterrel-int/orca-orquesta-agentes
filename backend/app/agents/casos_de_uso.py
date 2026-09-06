"""Registro de casos de uso seleccionables para el pipeline de agentes.

Cada caso define qué instrucción recibe el cerebro, qué código de respaldo se
usa cuando el cerebro guionado (o uno real que falla) no produce algo válido,
y a qué archivos escriben BackendAgent/FrontendAgent. `None`/"items" reproduce
exactamente el comportamiento histórico del pipeline: las constantes que antes
vivían en backend_agent.py/frontend_agent.py se movieron aquí tal cual, sin
reescribir su texto.

`app/agents/` queda fuera del esquema de puertos y adaptadores (ver
CLAUDE.md): es lógica de aplicación, así que este módulo puede importar
`app.config` sin problema — lo que no puede es `app.dominio` importar de acá.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import config
from .plantillas import LISTA_ITEMS_TSX, ROUTER_ITEMS
from .plantillas_calculadora import CALCULADORA_TSX, ROUTER_CALCULADORA
from .plantillas_encuesta import ENCUESTA_TSX, ROUTER_ENCUESTA
from .plantillas_leads import FORMULARIO_LEADS_TSX, ROUTER_LEADS


@dataclass(frozen=True)
class CasoDeUso:
    """Metadata expuesta al frontend vía GET /api/casos-de-uso."""

    id: str
    nombre: str
    descripcion: str
    icono: str


@dataclass(frozen=True)
class _DefinicionCaso:
    """Lo que necesitan BackendAgent/FrontendAgent para generar código de este caso."""

    prefijo_rutas: str
    rutas: tuple[str, ...]

    # --- backend ---
    mensaje_modelo_backend: str
    contexto_backend: str
    instruccion_backend: str
    respaldo_backend: str
    archivo_backend: str
    mensaje_generando_backend: str
    pasos_extra_backend: tuple[str, ...] = field(default_factory=tuple)

    # --- frontend ---
    instruccion_frontend: str = ""
    respaldo_frontend: str = ""
    archivo_frontend: str = ""
    mensaje_generando_frontend: str = ""
    pasos_extra_frontend: tuple[str, ...] = field(default_factory=tuple)


# --- items (comportamiento histórico, sin cambios) ---

_INSTRUCCION_BACKEND_ITEMS = (
    "Escribe un router de FastAPI con CRUD completo para la entidad Item "
    "(id, name). Usa SQLAlchemy async, dependencia obtener_sesion y los "
    "esquemas ItemCrear/ItemActualizar/ItemLeer ya existentes. "
    "Devuelve solo código Python, sin explicación ni cercas de markdown."
)

_INSTRUCCION_FRONTEND_ITEMS = (
    "Escribe un componente cliente de React para Next.js App Router que liste, "
    "cree y elimine items consumiendo el helper @/lib/api. TypeScript, sin "
    "librerías externas, con estados de carga, error y vacío. "
    "Devuelve solo el código, sin explicación ni cercas de markdown."
)

_ITEMS = _DefinicionCaso(
    prefijo_rutas="/api/items",
    rutas=(
        "GET /api/items",
        "POST /api/items",
        "GET /api/items/{id}",
        "PUT /api/items/{id}",
        "DELETE /api/items/{id}",
    ),
    mensaje_modelo_backend="Definiendo el modelo Item (id, name, creado_en)",
    contexto_backend="Modelo: Item(id: int, name: str). Prefijo: /api/items",
    instruccion_backend=_INSTRUCCION_BACKEND_ITEMS,
    respaldo_backend=ROUTER_ITEMS,
    archivo_backend="item_routes.py",
    mensaje_generando_backend="Generando el router CRUD de FastAPI",
    instruccion_frontend=_INSTRUCCION_FRONTEND_ITEMS,
    respaldo_frontend=LISTA_ITEMS_TSX,
    archivo_frontend="ListaItems.tsx",
    mensaje_generando_frontend="Generando el componente ListaItems",
)


# --- calculadora con login e historial ---

_CALCULADORA = _DefinicionCaso(
    prefijo_rutas="/api/calculadora",
    rutas=(
        "POST /api/calculadora/registro",
        "POST /api/calculadora/login",
        "POST /api/calculadora/operar",
        "GET /api/calculadora/historial",
    ),
    mensaje_modelo_backend="Diseñando el modelo de datos (usuarios, sesiones, operaciones)",
    contexto_backend=(
        "Prefijo: /api/calculadora. Tablas propias: usuarios, sesiones, operaciones."
    ),
    instruccion_backend=(
        "Escribe un router de FastAPI con prefijo /api/calculadora que reutilice "
        "Base/FabricaSesion de persistencia_sqlalchemy con tablas propias (usuarios, "
        "sesiones, operaciones). Endpoints: POST /registro (usuario, clave; hashea con "
        "hashlib.pbkdf2_hmac + salt de secrets.token_hex, 409 si el usuario ya existe), "
        "POST /login (valida la clave y devuelve un token de sesión), POST /operar "
        "(autenticado con Authorization: Bearer <token>; +,-,*,/ con división por cero "
        "controlada), GET /historial (autenticado, más recientes primero). "
        "Devuelve solo código Python, sin explicación ni cercas de markdown."
    ),
    respaldo_backend=ROUTER_CALCULADORA,
    archivo_backend="calculadora_routes.py",
    mensaje_generando_backend="Generando el router de la calculadora",
    pasos_extra_backend=("Escribiendo autenticación (pbkdf2_hmac + salt + tokens de sesión)",),
    instruccion_frontend=(
        "Escribe un componente cliente de React (Next.js App Router, TypeScript) para "
        "el caso 'calculadora': login/registro contra /api/calculadora, teclado de "
        "operaciones (+,-,*,/), tabla de historial y cierre de sesión con el token en "
        "localStorage. Sin librerías externas. Devuelve solo el código, sin explicación "
        "ni cercas de markdown."
    ),
    respaldo_frontend=CALCULADORA_TSX,
    archivo_frontend="Calculadora.tsx",
    mensaje_generando_frontend="Generando el componente Calculadora",
    pasos_extra_frontend=("Diseñando el flujo de login y registro",),
)


# --- leads de zapatillas ---

_LEADS = _DefinicionCaso(
    prefijo_rutas="/api/leads",
    rutas=("POST /api/leads", "GET /api/leads"),
    mensaje_modelo_backend="Diseñando el modelo de datos (leads)",
    contexto_backend="Prefijo: /api/leads. Tabla propia: leads_zapatillas.",
    instruccion_backend=(
        "Escribe un router de FastAPI con prefijo /api/leads que reutilice "
        "Base/FabricaSesion de persistencia_sqlalchemy con una tabla propia (nombre, "
        "email, telefono, talla, comentario, creado_en). POST / valida que nombre y "
        "email no estén vacíos y que el email tenga '@' (422 si no); GET / lista los "
        "leads más recientes primero. Sin autenticación: es una demo pública. "
        "Devuelve solo código Python, sin explicación ni cercas de markdown."
    ),
    respaldo_backend=ROUTER_LEADS,
    archivo_backend="leads_routes.py",
    mensaje_generando_backend="Generando el router de leads",
    pasos_extra_backend=("Diseñando el modelo de datos (leads)",),
    instruccion_frontend=(
        "Escribe un componente cliente de React (Next.js App Router, TypeScript) para "
        "el caso 'leads_zapatillas': formulario público (nombre, email, telefono, "
        "talla, comentario) que postea a /api/leads con validación básica y "
        "confirmación visual, más una tabla con los leads ya capturados (GET "
        "/api/leads). Sin librerías externas. Devuelve solo el código, sin explicación "
        "ni cercas de markdown."
    ),
    respaldo_frontend=FORMULARIO_LEADS_TSX,
    archivo_frontend="FormularioLeads.tsx",
    mensaje_generando_frontend="Generando el componente FormularioLeads",
    pasos_extra_frontend=("Diseñando el formulario público",),
)


# --- encuesta de satisfacción ---

_ENCUESTA = _DefinicionCaso(
    prefijo_rutas="/api/encuesta",
    rutas=("POST /api/encuesta", "GET /api/encuesta/resultados"),
    mensaje_modelo_backend="Diseñando el modelo de datos (respuestas 1-5)",
    contexto_backend="Prefijo: /api/encuesta. Tabla propia: encuesta_respuestas.",
    instruccion_backend=(
        "Escribe un router de FastAPI con prefijo /api/encuesta que reutilice "
        "Base/FabricaSesion de persistencia_sqlalchemy con una tabla propia (puntaje "
        "1-5, comentario opcional, creado_en). POST / rechaza puntaje fuera de 1-5 "
        "(422); GET /resultados devuelve total de respuestas, promedio y conteo por "
        "puntaje (1..5). Devuelve solo código Python, sin explicación ni cercas de "
        "markdown."
    ),
    respaldo_backend=ROUTER_ENCUESTA,
    archivo_backend="encuesta_routes.py",
    mensaje_generando_backend="Generando el router de la encuesta",
    pasos_extra_backend=("Diseñando el modelo de datos (respuestas 1-5)",),
    instruccion_frontend=(
        "Escribe un componente cliente de React (Next.js App Router, TypeScript) para "
        "el caso 'encuesta': selector de puntaje 1-5 con comentario opcional que "
        "postea a /api/encuesta, y una sección de resultados agregados (barras con "
        "div+CSS) usando GET /api/encuesta/resultados. Sin librerías externas. "
        "Devuelve solo el código, sin explicación ni cercas de markdown."
    ),
    respaldo_frontend=ENCUESTA_TSX,
    archivo_frontend="Encuesta.tsx",
    mensaje_generando_frontend="Generando el componente Encuesta",
    pasos_extra_frontend=("Diseñando la vista de resultados agregados",),
)


REGISTRO: dict[str, _DefinicionCaso] = {
    "items": _ITEMS,
    "calculadora": _CALCULADORA,
    "leads_zapatillas": _LEADS,
    "encuesta": _ENCUESTA,
}


CASOS_DE_USO: list[CasoDeUso] = [
    CasoDeUso(
        id="items",
        nombre="Corrida clásica (Items)",
        descripcion="El CRUD original de Item: alta, listado y borrado.",
        icono="📦",
    ),
    CasoDeUso(
        id="calculadora",
        nombre="Calculadora con login e historial",
        descripcion="Registro, login y una calculadora que guarda cada operación por usuario.",
        icono="🧮",
    ),
    CasoDeUso(
        id="leads_zapatillas",
        nombre="Leads de zapatillas",
        descripcion="Formulario público de captación de leads para una tienda de zapatillas.",
        icono="👟",
    ),
    CasoDeUso(
        id="encuesta",
        nombre="Encuesta de satisfacción",
        descripcion="Encuesta de 1 a 5 con resultados agregados en vivo.",
        icono="📊",
    ),
]


def resolver_caso(caso_de_uso: str | None) -> _DefinicionCaso:
    """None y "items" son el mismo caso: el comportamiento histórico."""
    return REGISTRO[caso_de_uso or "items"]


def destino_backend() -> Path:
    """Los cuatro casos comparten el mismo directorio raíz; solo cambia el archivo."""
    return Path(config.dir_generado_backend)


def destino_frontend(caso_de_uso: str | None) -> Path:
    """Items sigue escribiendo donde siempre; los casos nuevos van a su propia carpeta."""
    if caso_de_uso in (None, "items"):
        return Path(config.dir_generado_frontend)
    return Path(config.dir_generado_frontend_casos) / caso_de_uso


def archivos_backend_generados() -> list[str]:
    """Nombres de archivo (bajo dir_generado_backend) que puede haber escrito el
    BackendAgent, uno por caso registrado, sin duplicados. main.py los usa para
    montar todos los routers generados que existan en disco.
    """
    vistos: set[str] = set()
    archivos: list[str] = []
    for definicion in REGISTRO.values():
        if definicion.archivo_backend not in vistos:
            vistos.add(definicion.archivo_backend)
            archivos.append(definicion.archivo_backend)
    return archivos
