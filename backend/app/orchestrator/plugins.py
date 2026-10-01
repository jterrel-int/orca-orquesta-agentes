"""Plugins de ciclo de vida del Líder: extender la fábrica sin tocar su código.

Un plugin es un archivo .py en FABRICA_DIR_PLUGINS (por defecto
backend/plugins/) con una función `registrar(plugins)` que se suscribe a
eventos:

    def registrar(plugins):
        plugins.al("especificacion_aprobada", avisar_a_slack)
        plugins.compuerta("antes_de_aprobar", vetar_si_usa_eval)

Eventos (todos reciben argumentos con nombre):

    encargo_creado            encargo_id, pedido
    especificaciones_listas   encargo_id, especificaciones
    rechazo                   encargo_id, espec_id, intento, motivo, causa
    especificacion_aprobada   encargo_id, espec_id, intentos
    especificacion_fallida    encargo_id, espec_id, motivo
    encargo_terminado         encargo_id, estado, costo_usd

Compuertas (pueden vetar devolviendo un texto con el motivo; None = pasa):

    antes_de_aprobar          encargo_id, espec_id, espacio, archivos

Un veto se trata como un rechazo más: entra al mismo ciclo de reintentos.

Un plugin que explota no tumba el encargo: el error se registra y el
pipeline sigue — salvo en una compuerta, donde un error cuenta como veto
(fallar cerrado: una validación que no corrió no aprobó nada).
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

EVENTOS = frozenset(
    {
        "encargo_creado",
        "especificaciones_listas",
        "rechazo",
        "especificacion_aprobada",
        "especificacion_fallida",
        "encargo_terminado",
    }
)
COMPUERTAS = frozenset({"antes_de_aprobar"})

Gancho = Callable[..., Any]


class RegistroPlugins:
    def __init__(self) -> None:
        self._ganchos: dict[str, list[tuple[str, Gancho]]] = {}
        self._compuertas: dict[str, list[tuple[str, Gancho]]] = {}
        self.cargados: list[str] = []
        self.errores: list[str] = []
        self._origen = "codigo"

    def al(self, evento: str, fn: Gancho) -> None:
        if evento not in EVENTOS:
            raise ValueError(f"Evento desconocido: {evento}. Válidos: {sorted(EVENTOS)}")
        self._ganchos.setdefault(evento, []).append((self._origen, fn))

    def compuerta(self, nombre: str, fn: Gancho) -> None:
        if nombre not in COMPUERTAS:
            raise ValueError(f"Compuerta desconocida: {nombre}. Válidas: {sorted(COMPUERTAS)}")
        self._compuertas.setdefault(nombre, []).append((self._origen, fn))

    async def disparar(self, evento: str, **datos: Any) -> list[str]:
        """Devuelve los errores de los plugins que fallaron (para la bitácora)."""
        errores: list[str] = []
        for origen, fn in self._ganchos.get(evento, []):
            try:
                resultado = fn(**datos)
                if inspect.isawaitable(resultado):
                    await resultado
            except Exception as e:  # noqa: BLE001 — un plugin no tumba el encargo
                log.exception("El plugin %s falló en %s", origen, evento)
                errores.append(f"{origen}: {type(e).__name__}: {e}")
        return errores

    async def evaluar(self, nombre: str, **datos: Any) -> str | None:
        """El primer veto, con el plugin que lo emitió; None si todos dejan pasar."""
        for origen, fn in self._compuertas.get(nombre, []):
            try:
                resultado = fn(**datos)
                if inspect.isawaitable(resultado):
                    resultado = await resultado
            except Exception as e:  # noqa: BLE001
                log.exception("La compuerta %s del plugin %s falló", nombre, origen)
                return f"[{origen}] la validación falló ({type(e).__name__}: {e})"
            if resultado:
                return f"[{origen}] {resultado}"
        return None

    def cargar_directorio(self, directorio: Path) -> None:
        """Importa cada .py del directorio (en orden alfabético, salteando los
        que empiezan con "_") y llama a su `registrar(self)`.
        """
        if not directorio.is_dir():
            return
        for archivo in sorted(directorio.glob("*.py")):
            if archivo.name.startswith("_"):
                continue
            nombre = f"orquesta_plugin_{archivo.stem}"
            try:
                spec = importlib.util.spec_from_file_location(nombre, archivo)
                if spec is None or spec.loader is None:
                    continue
                modulo = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modulo)
                registrar = getattr(modulo, "registrar", None)
                if not callable(registrar):
                    self.errores.append(f"{archivo.name}: no define registrar(plugins)")
                    continue
                self._origen = archivo.stem
                registrar(self)
                self.cargados.append(archivo.stem)
            except Exception as e:  # noqa: BLE001 — un plugin roto no impide arrancar
                log.exception("No se pudo cargar el plugin %s", archivo)
                self.errores.append(f"{archivo.name}: {type(e).__name__}: {e}")
            finally:
                self._origen = "codigo"
