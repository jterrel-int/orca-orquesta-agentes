"""Configuración del proceso. Todo por variables de entorno, nada hardcodeado."""

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
    # humano lo pida es un incidente esperando a ocurrir. Con esto en false el
    # DeployAgent registra el comando exacto que ejecutaría y termina en 'done'.
    deploy_enabled: bool = False
    vercel_token: str | None = None
    vercel_cwd: str = str(RAIZ_PROYECTO / "frontend")
    deploy_timeout_s: int = 600

    # --- cerebro de los agentes ---
    # 'scripted' usa pasos deterministas (por defecto, no necesita clave).
    # 'anthropic' usa la API real; requiere anthropic_api_key.
    brain: str = "scripted"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    # --- rutas de generación ---
    dir_generado_backend: str = str(RAIZ_BACKEND / "app" / "generated")
    dir_generado_frontend: str = str(RAIZ_PROYECTO / "frontend" / "app" / "items")
    # Raíz para los casos de uso nuevos (calculadora, leads, encuesta): cada uno
    # escribe su componente bajo dir_generado_frontend_casos/<caso>/. "items"
    # sigue usando dir_generado_frontend de arriba, sin cambios.
    dir_generado_frontend_casos: str = str(RAIZ_PROYECTO / "frontend" / "app" / "casos")

    # --- ritmo de la demo ---
    # Duración de cada sub-paso adicional que loguean BackendAgent/FrontendAgent
    # para los casos de uso nuevos (calculadora, leads, encuesta) — "items" no
    # los usa y no cambia su timing. El default de acá es el de producción:
    # apunta a que una corrida completa de un caso nuevo se sienta como una
    # demo real (~4-6 minutos). Los tests que ejercitan estos agentes
    # directamente bajan este valor con monkeypatch antes de correr, así la
    # suite no se vuelve lenta.
    duracion_paso_demo_s: float = 40.0

    # --- backlog ---
    ruta_backlog: str = str(RAIZ_PROYECTO / "docs" / "BACKLOG.md")

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

        if self.deploy_enabled and shutil.which("vercel") is None:
            avisos.append(
                "DEPLOY_ENABLED=true pero el CLI de Vercel no está instalado o no está en el PATH"
            )

        if self.deploy_enabled and not Path(self.vercel_cwd).is_dir():
            avisos.append(
                f"DEPLOY_ENABLED=true pero el directorio del frontend no existe: {self.vercel_cwd}"
            )

        return avisos


config = Config()
