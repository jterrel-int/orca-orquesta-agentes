"""Cableado: qué implementación concreta de cada puerto se usa, según config.

Los agentes y el Líder reciben sus puertos por constructor; este es el único
lugar que decide entre implementaciones — ni los agentes ni el Líder tienen
un `if` sobre config.brain o config.deploy_enabled.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from ..config import config
from ..dominio.fabrica import ModoAprobacion, PoliticaFabrica
from ..dominio.puertos import (
    Cerebro,
    CerebroMedido,
    Desplegador,
    EjecutorPruebas,
    RepositorioCredencialAnthropic,
)
from ..dominio.salud import ServicioSaludFabrica
from ..orchestrator.lider import LiderFabrica
from ..orchestrator.plugins import RegistroPlugins
from ..orchestrator.prefect_opcional import prefect_disponible
from . import persistencia_sqlalchemy as persistencia
from .bus_memoria import bus
from .cache_llm import CerebroConCache
from .cerebro_anthropic import CerebroAnthropic
from .cerebro_claude_cli import CerebroClaudeCLI, cuenta_claude_cli
from .cerebro_guionado import CerebroGuionado
from .cerebro_openai_compatible import CerebroOpenAICompatible
from .despliegue_github import DespliegueGitHub, DespliegueGitHubSimulado
from .ejecutor_pruebas import EjecutorDocker, EjecutorLocal
from .persistencia_fabrica import (
    BitacoraSQLAlchemy,
    RepositorioEncargosSQLAlchemy,
    RepositorioMetricasSQLAlchemy,
    tablas_existentes,
)

log = logging.getLogger(__name__)


async def _api_key_anthropic(
    credenciales: RepositorioCredencialAnthropic | None,
) -> tuple[str | None, str | None]:
    """Devuelve (api_key, fuente) — la key guardada desde Configuración tiene
    prioridad sobre ANTHROPIC_API_KEY. `fuente` es para mostrar en /api/health, nunca
    la key en sí.
    """
    if credenciales is None:
        from .persistencia_sqlalchemy import FabricaSesion, RepositorioCredencialAnthropicSQLAlchemy

        async with FabricaSesion() as sesion:
            credencial = await RepositorioCredencialAnthropicSQLAlchemy(sesion).obtener()
    else:
        credencial = await credenciales.obtener()

    if credencial is not None:
        return credencial.api_key, "guardada en Configuración"
    if config.anthropic_api_key:
        return config.anthropic_api_key, "variable de entorno ANTHROPIC_API_KEY"
    return None, None


async def _registrar_uso_anthropic(tokens: int) -> None:
    """Abre su propia sesión: a diferencia de los repos de arriba, este
    callback vive tanto como el Cerebro (toda la corrida), no solo un request.
    """
    from .persistencia_sqlalchemy import FabricaSesion, RepositorioUsoAnthropicSQLAlchemy

    async with FabricaSesion() as sesion:
        await RepositorioUsoAnthropicSQLAlchemy(sesion).sumar_tokens(tokens)


async def construir_cerebro(
    credenciales: RepositorioCredencialAnthropic | None = None,
    *,
    modelo: str | None = None,
) -> Cerebro:
    """Si no hay ninguna API key (ni guardada ni por variable de entorno), cae
    a guionado y lo avisa. BRAIN=claude-cli no pasa por ninguna key: delega en
    el CLI de Claude Code ya logueado en esta máquina (ver cerebro_claude_cli.py).

    `modelo` pisa el modelo por defecto del proveedor activo — la fábrica lo
    usa para asignar un modelo por rol (ver construir_cerebro_para_rol).
    """
    if config.brain == "claude-cli":
        log.info("Cerebro Claude CLI activo (%s)", config.claude_cli_comando)
        return CerebroClaudeCLI(config.claude_cli_comando, config.claude_cli_timeout_s)

    if config.brain == "openai-compatible":
        if not config.openai_compat_api_key:
            log.warning("BRAIN=openai-compatible pero falta OPENAI_COMPAT_API_KEY; guionado")
            return CerebroGuionado()
        return CerebroOpenAICompatible(
            config.openai_compat_api_key,
            modelo or config.openai_compat_modelo,
            config.openai_compat_base_url,
        )

    api_key, fuente = await _api_key_anthropic(credenciales)
    if api_key is None:
        if config.brain == "anthropic":
            log.warning("BRAIN=anthropic pero falta una API key de Anthropic; se usa el guionado")
        return CerebroGuionado()
    log.info("Cerebro Anthropic activo (%s)", fuente)
    return CerebroAnthropic(
        api_key, modelo or config.anthropic_model, registrar_uso=_registrar_uso_anthropic
    )


async def estado_cerebro(
    credenciales: RepositorioCredencialAnthropic | None = None,
) -> dict[str, str | None]:
    """Para /api/health y Configuración: qué cerebro está activo ahora mismo y
    de dónde sale la clave — nunca la clave en sí. `cuenta` solo se completa
    con claude-cli: quien tiene varias cuentas de Claude logueadas en esta
    máquina necesita poder confirmar cuál es la que van a gastar las corridas.
    """
    if config.brain == "openai-compatible":
        hay_clave = bool(config.openai_compat_api_key)
        return {
            "activo": "openai-compatible" if hay_clave else "scripted",
            "modelo": config.openai_compat_modelo if hay_clave else None,
            "fuente": config.openai_compat_base_url if hay_clave else None,
            "cuenta": None,
        }

    if config.brain == "claude-cli":
        cuenta = await cuenta_claude_cli(config.claude_cli_comando)
        return {
            "activo": "claude-cli",
            "modelo": None,
            "fuente": config.claude_cli_comando,
            "cuenta": cuenta,
        }

    api_key, fuente = await _api_key_anthropic(credenciales)
    if api_key is None:
        return {"activo": "scripted", "modelo": None, "fuente": None, "cuenta": None}
    return {
        "activo": "anthropic",
        "modelo": config.anthropic_model,
        "fuente": fuente,
        "cuenta": None,
    }


# --- fábrica de software ---

_MODELO_POR_ROL: dict[str, Callable[[], str]] = {
    "especificador": lambda: config.fabrica_modelo_especificador,
    "implementador": lambda: config.fabrica_modelo_implementador,
    "revisor": lambda: config.fabrica_modelo_revisor,
    "diagnosticador": lambda: config.fabrica_modelo_diagnosticador,
}


def _modelo_por_defecto() -> str:
    if config.brain == "openai-compatible":
        return config.openai_compat_modelo
    return config.anthropic_model


async def construir_cerebro_para_rol(rol: str) -> Cerebro:
    """El mismo proveedor para todos los roles; el modelo puede cambiar por
    rol (FABRICA_MODELO_<ROL>). Vacío = el modelo por defecto del proveedor.

    Con FABRICA_CACHE_LLM=true, un cerebro real queda envuelto en la caché
    de respuestas (ver cache_llm.py). El guionado no: ya es determinista y
    gratis.
    """
    elegir = _MODELO_POR_ROL.get(rol)
    modelo = (elegir() if elegir else "") or None
    cerebro = await construir_cerebro(modelo=modelo)
    if (
        config.fabrica_cache_llm
        and isinstance(cerebro, CerebroMedido)
        and not isinstance(cerebro, CerebroGuionado)
    ):
        return CerebroConCache(cerebro, modelo or _modelo_por_defecto(), persistencia.FabricaSesion)
    return cerebro


def construir_ejecutor_pruebas() -> EjecutorPruebas:
    if config.fabrica_sandbox == "docker":
        return EjecutorDocker(config.fabrica_imagen_sandbox)
    return EjecutorLocal()


def construir_ejecutor_e2e() -> EjecutorPruebas | None:
    """None = pruebas funcionales apagadas; el Verificador lo informa como
    omitido en vez de fingir que pasaron. Playwright necesita red para
    llegar a la app, por eso este contenedor no usa --network none.
    """
    if not config.fabrica_e2e_enabled:
        return None
    return EjecutorDocker(config.fabrica_imagen_e2e, red="bridge")


def construir_desplegador_fabrica(espacio: Path, encargo_id: str, titulo: str) -> Desplegador:
    rama = f"fabrica/{encargo_id}"
    if not config.deploy_enabled:
        return DespliegueGitHubSimulado(
            espacio, rama, config.github_repo, config.github_rama_base, titulo
        )
    return DespliegueGitHub(espacio, rama, config.github_repo, config.github_rama_base, titulo)


_lider: LiderFabrica | None = None


def construir_lider_fabrica() -> LiderFabrica:
    """Un solo Líder por proceso: guarda las tareas en curso de cada encargo.
    La fábrica de sesiones se lee al construirlo (no al importar), así las
    pruebas pueden apuntarla a una base temporal.
    """
    global _lider
    if _lider is None:
        plugins = RegistroPlugins()
        usar_prefect = config.fabrica_orquestador == "prefect"
        if usar_prefect and not prefect_disponible():
            log.warning(
                "FABRICA_ORQUESTADOR=prefect pero el paquete no está instalado "
                "(pip install -r requirements-prefect.txt); se sigue sin Prefect"
            )
            usar_prefect = False
        plugins.cargar_directorio(Path(config.fabrica_dir_plugins))
        sesiones = persistencia.FabricaSesion
        modo: ModoAprobacion = "ambiguedad"
        if config.fabrica_aprobacion_humana == "nunca":
            modo = "nunca"
        elif config.fabrica_aprobacion_humana == "siempre":
            modo = "siempre"
        politica = PoliticaFabrica(
            max_intentos=max(1, config.fabrica_max_intentos),
            presupuesto_encargo_usd=config.fabrica_presupuesto_usd,
            aprobacion_humana=modo,
        )
        _lider = LiderFabrica(
            repositorio=RepositorioEncargosSQLAlchemy(sesiones),
            bitacora=BitacoraSQLAlchemy(sesiones),
            metricas=RepositorioMetricasSQLAlchemy(sesiones),
            bus=bus,
            politica=politica,
            dir_espacios=Path(config.fabrica_dir_espacios),
            cerebro_para=construir_cerebro_para_rol,
            ejecutor=construir_ejecutor_pruebas(),
            ejecutor_e2e=construir_ejecutor_e2e(),
            desplegador_para=construir_desplegador_fabrica,
            tablas_existentes=lambda: tablas_existentes(sesiones),
            timeout_pruebas_s=config.fabrica_timeout_pruebas_s,
            e2e_url_base=config.fabrica_e2e_url_base,
            plugins=plugins,
            limite_contexto=config.fabrica_limite_contexto,
            paralelismo=config.fabrica_paralelismo,
            usar_prefect=usar_prefect,
        )
        if plugins.cargados or plugins.errores:
            log.info("Plugins de la fábrica: %s · errores: %s", plugins.cargados, plugins.errores)
    return _lider


def construir_servicio_salud_fabrica() -> ServicioSaludFabrica:
    sesiones = persistencia.FabricaSesion
    return ServicioSaludFabrica(
        RepositorioEncargosSQLAlchemy(sesiones),
        RepositorioMetricasSQLAlchemy(sesiones),
        BitacoraSQLAlchemy(sesiones),
        config.fabrica_presupuesto_usd,
    )
