"""Adaptador simulado del puerto Desplegador: el modo DEPLOY_ENABLED=false.

Registra el comando exacto que se ejecutaría y termina bien; no simula un
despliegue exitoso ni toca la red.
"""

from __future__ import annotations

from ..config import config
from ..dominio.puertos import EmisorLinea


class DespliegueSimulado:
    async def ejecutar(self, on_linea: EmisorLinea) -> str | None:
        cmd_visible = "vercel --prod --yes" + (" --token ***" if config.vercel_token else "")
        await on_linea("DEPLOY_ENABLED=false — no se despliega")
        await on_linea(f"Comando que se ejecutaría: {cmd_visible}")
        await on_linea(f"Directorio: {config.vercel_cwd}")
        await on_linea("Activa DEPLOY_ENABLED=true en .env para desplegar de verdad")
        return None
