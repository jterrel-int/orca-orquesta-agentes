"""Configuración del proceso. Todo por variables de entorno, nada hardcodeado."""

import importlib.util
import shutil
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_BACKEND = Path(__file__).resolve().parent.parent
RAIZ_PROYECTO = RAIZ_BACKEND.parent


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- base de datos ---
    database_url: str = f"sqlite+aiosqlite:///{RAIZ_BACKEND / 'orquesta.db'}"

    # --- CORS ---
    origenes_permitidos: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- despliegue ---
    # Apagado a propósito. Un agente que despliega a producción sin que un
    # humano lo pida es un incidente esperando a ocurrir. Con esto en false la
    # etapa de Despliegue de la fábrica informa los comandos exactos que
    # correría (git + gh) y no publica nada.
    deploy_enabled: bool = False
    # Token de Vercel por variable de entorno; alternativa a conectar la
    # cuenta desde Configuración.
    vercel_token: str | None = None

    # --- cerebro de los agentes ---
    # 'scripted' usa pasos deterministas (por defecto, no necesita clave).
    # 'anthropic' usa la API real; requiere anthropic_api_key.
    # 'claude-cli' delega en el CLI de Claude Code ya logueado en esta máquina
    # (`claude -p`) en vez de una API key propia — sirve para desarrollo local
    # sin gastar saldo de la API, pero no funciona en un backend desplegado
    # (Render, etc.) porque ahí no hay ninguna sesión de Claude Code logueada.
    brain: str = "scripted"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    claude_cli_comando: str = "claude"
    # Una especificación grande (varios archivos) puede tardar más de 2 minutos
    # en claude-cli; si no alcanza, el Implementador queda con la plantilla.
    claude_cli_timeout_s: float = 300.0
    # 'openai-compatible': cualquier API con el formato de chat completions de
    # OpenAI. Por defecto apunta a DeepSeek — modelos más baratos para etapas
    # bien acotadas. El costo se calcula con TARIFAS_EXTRA (ver tarifas.py).
    openai_compat_api_key: str | None = None
    openai_compat_base_url: str = "https://api.deepseek.com"
    openai_compat_modelo: str = "deepseek-chat"
    # JSON {modelo: [USD por millón de entrada, USD por millón de salida]}
    # para modelos fuera de la tabla de Claude, p. ej. '{"deepseek-chat": [0.27, 1.1]}'.
    tarifas_extra: str = ""
    # Tope de salida de cada llamada. El Implementador devuelve archivos
    # completos en un JSON: con poco margen la respuesta llega cortada y el
    # encargo cae a la plantilla de respaldo.
    cerebro_max_tokens: int = 16000
    openai_compat_max_tokens: int = 8192
    # Por llamada HTTP. Los reintentos cubren 429/529/5xx y cortes de red.
    cerebro_timeout_s: float = 300.0
    cerebro_reintentos: int = 2

    # --- acceso ---
    # Si se define, toda la API (salvo /api/health) y el WebSocket exigen este
    # token: cabecera `Authorization: Bearer <token>` o `?token=` en /ws. El
    # panel lo manda si NEXT_PUBLIC_ORQUESTA_TOKEN tiene el mismo valor.
    # Recomendado si el backend escucha en algo que no sea localhost.
    orquesta_token: str | None = None

    # --- fábrica de software (orchestrator/lider.py) ---
    # Modelo por rol. Vacío = el del proveedor activo (anthropic_model u
    # openai_compat_modelo). Bajar el especificador/revisor/diagnosticador a
    # un modelo más barato es la palanca de costo más directa: el harness
    # valida su trabajo igual.
    fabrica_modelo_especificador: str = ""
    fabrica_modelo_implementador: str = ""
    fabrica_modelo_revisor: str = ""
    fabrica_modelo_diagnosticador: str = ""
    fabrica_dir_espacios: str = str(RAIZ_PROYECTO / "fabrica_espacios")
    fabrica_max_intentos: int = 2
    # Tope duro de intentos por especificación sumando los reintentos humanos.
    # Al llegar se cierra como fallida con un informe, en vez de seguir girando.
    fabrica_max_rondas: int = 6
    # Ninguna etapa puede tardar más que esto (s); 0 lo desactiva. Tiene que
    # ser mayor que CLAUDE_CLI_TIMEOUT_S y CEREBRO_TIMEOUT_S con sus reintentos.
    fabrica_timeout_etapa_s: float = 1200.0
    # Tope de gasto por encargo en USD; 0 lo desactiva.
    fabrica_presupuesto_usd: float = 1.0
    # 'ambiguedad': pregunta solo cuando el Especificador detecta un conflicto
    # (p. ej. una tabla legada) o una especificación riesgosa. 'nunca' toma la
    # primera opción de cada pregunta y lo deja en la bitácora. 'siempre'
    # pide aprobación humana para cada especificación.
    fabrica_aprobacion_humana: str = "ambiguedad"
    # Dónde corre el código generado para verificarlo: 'local' (subproceso,
    # sin claves en el entorno) o 'docker' (contenedor sin red). Con un
    # cerebro real, 'docker' es lo recomendable — ver advertencias().
    fabrica_sandbox: str = "local"
    fabrica_imagen_sandbox: str = "orquesta-sandbox:latest"
    fabrica_timeout_pruebas_s: float = 120.0
    # Pruebas funcionales con Playwright en un contenedor con Chromium.
    # Apagado por defecto: requiere Docker y una URL donde corra la app.
    fabrica_e2e_enabled: bool = False
    fabrica_imagen_e2e: str = "mcr.microsoft.com/playwright:v1.55.0-noble"
    fabrica_e2e_url_base: str = "http://host.docker.internal:3000"
    # Despliegue de un encargo vía GitHub (PR + GitHub Actions). Solo si
    # DEPLOY_ENABLED=true; si no, se informa qué se correría.
    github_repo: str | None = None
    github_rama_base: str = "main"
    # Caché de respuestas del LLM (ver adaptadores/cache_llm.py). Apagada por
    # defecto: fija la primera respuesta de cada prompt idéntico — más barato y
    # reproducible, pero deja de muestrear respuestas nuevas en un reintento.
    fabrica_cache_llm: bool = False
    # Plugins de ciclo de vida del Líder (ver orchestrator/plugins.py). Los
    # archivos que empiezan con "_" no se cargan.
    fabrica_dir_plugins: str = str(RAIZ_BACKEND / "plugins")
    # Tope de caracteres del contexto que se manda al cerebro en cada etapa.
    # Por encima, se compacta de forma determinista (ver agents/fabrica/comun.py).
    fabrica_limite_contexto: int = 60000
    # Cuántas especificaciones de un mismo nivel de dependencias se
    # construyen a la vez dentro de un encargo.
    fabrica_paralelismo: int = 3
    # 'local' (asyncio, por defecto) o 'prefect': cada encargo se registra
    # como flow run y cada etapa como task run en la UI de Prefect. Requiere
    # `pip install -r requirements-prefect.txt`. Prefect observa; el Líder
    # sigue decidiendo (ver orchestrator/prefect_opcional.py).
    fabrica_orquestador: str = "local"
    # Para enlazar desde el panel a la UI de Prefect.
    prefect_ui_url: str = "http://127.0.0.1:4200"

    # --- integración OAuth con Vercel ---
    # Se registra a mano en vercel.com/dashboard → Integrations Console. Sin
    # estas tres, /api/vercel/oauth/iniciar responde 500 en vez de adivinar.
    vercel_client_id: str | None = None
    vercel_client_secret: str | None = None
    vercel_integration_slug: str | None = None
    vercel_oauth_redirect_uri: str = "http://localhost:8000/api/vercel/oauth/callback"

    # --- conexión con Render ---
    # Sin OAuth de parte de Render: es una API key pegada a mano y verificada
    # contra su API antes de guardarla.
    render_service_name: str = "orquesta-backend"

    @property
    def lista_origenes(self) -> list[str]:
        return [o.strip() for o in self.origenes_permitidos.split(",") if o.strip()]

    def advertencias(self) -> list[str]:
        """Configuración que no impide arrancar pero probablemente no es la que
        la persona quiere — por ejemplo, cayó a un respaldo silenciosamente.
        `/api/health` la expone para que el panel la muestre en vez de que
        alguien la descubra mirando los logs.
        """
        avisos: list[str] = []

        if self.brain == "anthropic" and not self.anthropic_api_key:
            avisos.append(
                "BRAIN=anthropic pero falta ANTHROPIC_API_KEY; se está usando el cerebro guionado"
            )

        if self.brain == "claude-cli" and shutil.which(self.claude_cli_comando) is None:
            avisos.append(f"BRAIN=claude-cli pero '{self.claude_cli_comando}' no está en el PATH")

        if self.brain == "openai-compatible" and not self.openai_compat_api_key:
            avisos.append(
                "BRAIN=openai-compatible pero falta OPENAI_COMPAT_API_KEY; "
                "se está usando el cerebro guionado"
            )

        if self.brain != "scripted" and self.fabrica_sandbox == "local":
            avisos.append(
                "La fábrica verifica código generado por un LLM en un subproceso local; "
                "FABRICA_SANDBOX=docker lo aísla en un contenedor sin red"
            )

        if self.fabrica_aprobacion_humana not in ("nunca", "ambiguedad", "siempre"):
            avisos.append(
                f"FABRICA_APROBACION_HUMANA='{self.fabrica_aprobacion_humana}' no es válido; "
                "se usa 'ambiguedad'"
            )

        if self.fabrica_orquestador == "prefect" and importlib.util.find_spec("prefect") is None:
            avisos.append(
                "FABRICA_ORQUESTADOR=prefect pero Prefect no está instalado "
                "(pip install -r requirements-prefect.txt); la fábrica corre sin él"
            )

        if "*" in self.lista_origenes:
            avisos.append(
                "ORIGENES_PERMITIDOS incluye '*': cualquier página web podría usar la API "
                "desde el navegador de quien tenga el panel abierto"
            )

        if 0 < self.fabrica_timeout_etapa_s <= self.claude_cli_timeout_s and (
            self.brain == "claude-cli"
        ):
            avisos.append(
                "FABRICA_TIMEOUT_ETAPA_S es menor que CLAUDE_CLI_TIMEOUT_S: las etapas se "
                "cortarán antes de que el CLI pueda responder"
            )

        if self.deploy_enabled and not self.github_repo:
            avisos.append("DEPLOY_ENABLED=true pero falta GITHUB_REPO (dueño/repositorio)")

        for ejecutable in ("git", "gh"):
            if self.deploy_enabled and shutil.which(ejecutable) is None:
                avisos.append(f"DEPLOY_ENABLED=true pero '{ejecutable}' no está en el PATH")

        return avisos


config = Config()
