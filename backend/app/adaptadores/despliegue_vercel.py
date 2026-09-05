"""Adaptador real del puerto Desplegador: ejecuta `vercel --prod` como subproceso.

Es el único adaptador con efectos fuera del repositorio. Por eso DeployAgent
solo lo usa cuando DEPLOY_ENABLED=true (ver adaptadores/fabricas.py).
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from ..config import config
from ..dominio.errores import DespliegueFallido
from ..dominio.puertos import EmisorLinea


class DespliegueVercel:
    """Si no se pasa `token`, usa VERCEL_TOKEN; si tampoco hay, la sesión local del CLI."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token if token is not None else config.vercel_token

    async def ejecutar(self, on_linea: EmisorLinea) -> str | None:
        cmd = ["vercel", "--prod", "--yes"]
        if self._token:
            cmd += ["--token", self._token]

        if shutil.which("vercel") is None:
            raise DespliegueFallido(
                "El CLI de Vercel no está instalado o no está en el PATH. "
                "Instálalo con: npm i -g vercel"
            )

        cwd = Path(config.vercel_cwd)
        if not cwd.is_dir():
            raise DespliegueFallido(f"El directorio del frontend no existe: {cwd}")

        visible = " ".join("--token ***" if c == self._token else c for c in cmd)
        await on_linea(f"Ejecutando: {visible}")

        proceso = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        url_produccion: str | None = None

        async def bombear() -> None:
            nonlocal url_produccion
            assert proceso.stdout is not None
            async for linea in proceso.stdout:
                texto = linea.decode("utf-8", errors="replace").rstrip()
                if not texto:
                    continue
                if "https://" in texto and url_produccion is None:
                    url_produccion = texto[texto.index("https://") :].split()[0]
                await on_linea(texto)

        try:
            await asyncio.wait_for(bombear(), timeout=config.deploy_timeout_s)
            codigo = await asyncio.wait_for(proceso.wait(), timeout=30)
        except TimeoutError:
            proceso.kill()
            await proceso.wait()
            raise DespliegueFallido(
                f"El despliegue superó el tiempo límite de {config.deploy_timeout_s}s"
            ) from None

        if codigo != 0:
            raise DespliegueFallido(f"vercel --prod terminó con código {codigo}")

        return url_produccion
