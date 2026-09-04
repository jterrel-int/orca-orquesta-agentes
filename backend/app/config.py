"""Configuración del proceso. Todo por variables de entorno, nada hardcodeado."""

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

    @property
    def lista_origenes(self) -> list[str]:
        return [o.strip() for o in self.origenes_permitidos.split(",") if o.strip()]


config = Config()
