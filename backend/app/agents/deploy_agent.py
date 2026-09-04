"""Agente 3: despliega el frontend a Vercel.

Este es el único agente con efectos fuera del repositorio, así que es el único
que está apagado por defecto. Con DEPLOY_ENABLED=false registra el comando
exacto que ejecutaría y termina bien; no simula un despliegue exitoso.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from ..config import config
from .base import Agente, ContextoCorrida


class DeployAgent(Agente):
    name = "deploy"

    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        cmd = ["vercel", "--prod", "--yes"]
        if config.vercel_token:
            cmd += ["--token", config.vercel_token]

        visible = " ".join("--token ***" if c == config.vercel_token else c for c in cmd)

        if not config.deploy_enabled:
            await self.log(ctx, "DEPLOY_ENABLED=false — no se despliega")
            await self.log(ctx, f"Comando que se ejecutaría: {visible}")
            await self.log(ctx, f"Directorio: {config.vercel_cwd}")
            await self.log(ctx, "Activa DEPLOY_ENABLED=true en .env para desplegar de verdad")
            ctx.datos["deploy"] = "omitido"
            return []

        if shutil.which("vercel") is None:
            raise RuntimeError(
                "El CLI de Vercel no está instalado o no está en el PATH. "
                "Instálalo con: npm i -g vercel"
            )

        cwd = Path(config.vercel_cwd)
        if not cwd.is_dir():
            raise RuntimeError(f"El directorio del frontend no existe: {cwd}")

        await self.log(ctx, f"Ejecutando: {visible}")

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
                    url_produccion = texto[texto.index("https://"):].split()[0]
                await self.log(ctx, texto)

        try:
            await asyncio.wait_for(bombear(), timeout=config.deploy_timeout_s)
            codigo = await asyncio.wait_for(proceso.wait(), timeout=30)
        except asyncio.TimeoutError:
            proceso.kill()
            await proceso.wait()
            raise RuntimeError(
                f"El despliegue superó el tiempo límite de {config.deploy_timeout_s}s"
            ) from None

        if codigo != 0:
            raise RuntimeError(f"vercel --prod terminó con código {codigo}")

        if url_produccion:
            ctx.datos["url_produccion"] = url_produccion
            await self.log(ctx, f"Desplegado en {url_produccion}")

        ctx.datos["deploy"] = "ok"
        return [url_produccion] if url_produccion else []
