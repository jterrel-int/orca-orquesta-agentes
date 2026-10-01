"""Despliegue de un encargo de la fábrica vía GitHub: rama + commit + push +
pull request. El CI/CD lo corre GitHub Actions con el workflow que la etapa
de despliegue deja en `.github/workflows/ci.yml` del espacio de trabajo.

Mismo criterio que Vercel: con DEPLOY_ENABLED=false se usa el simulado, que
solo informa los comandos exactos que correría (ver fabricas.py).
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

from ..dominio.errores import DespliegueFallido
from ..dominio.puertos import EmisorLinea


def _comandos(rama: str, repo: str, base: str, titulo: str) -> list[list[str]]:
    return [
        ["git", "init", "-b", base],
        ["git", "checkout", "-B", rama],
        ["git", "add", "-A"],
        ["git", "commit", "-m", titulo],
        ["git", "push", "-u", f"https://github.com/{repo}.git", rama],
        ["gh", "pr", "create", "--repo", repo, "--base", base, "--head", rama,
         "--title", titulo, "--body", "Generado por la fábrica de Orquesta."],
    ]  # fmt: skip


class DespliegueGitHubSimulado:
    def __init__(self, espacio: Path, rama: str, repo: str | None, base: str, titulo: str) -> None:
        self._espacio = espacio
        self._rama = rama
        self._repo = repo or "<GITHUB_REPO sin configurar>"
        self._base = base
        self._titulo = titulo

    async def ejecutar(self, on_linea: EmisorLinea) -> str | None:
        await on_linea("DEPLOY_ENABLED=false — no se publica nada")
        await on_linea(f"Espacio de trabajo: {self._espacio}")
        for cmd in _comandos(self._rama, self._repo, self._base, self._titulo):
            await on_linea(f"Comando que se ejecutaría: {' '.join(cmd)}")
        await on_linea("GitHub Actions correría .github/workflows/ci.yml sobre el PR")
        return None


class DespliegueGitHub:
    """Usa la sesión de `gh` ya autenticada en esta máquina (gh auth login);
    el token nunca pasa por Orquesta.
    """

    def __init__(self, espacio: Path, rama: str, repo: str | None, base: str, titulo: str) -> None:
        self._espacio = espacio
        self._rama = rama
        self._repo = repo
        self._base = base
        self._titulo = titulo

    async def ejecutar(self, on_linea: EmisorLinea) -> str | None:
        if not self._repo:
            raise DespliegueFallido("Falta GITHUB_REPO (formato dueño/repositorio) en .env")
        for ejecutable in ("git", "gh"):
            if shutil.which(ejecutable) is None:
                raise DespliegueFallido(f"'{ejecutable}' no está instalado o no está en el PATH")

        url: str | None = None
        for cmd in _comandos(self._rama, self._repo, self._base, self._titulo):
            await on_linea(f"$ {' '.join(cmd)}")
            # En un hilo: ver el motivo en ejecutor_pruebas._correr.
            r = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(self._espacio),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            texto = r.stdout.decode("utf-8", errors="replace").strip() if r.stdout else ""
            for linea in texto.splitlines()[-5:]:
                await on_linea(linea)
            if r.returncode != 0:
                raise DespliegueFallido(f"Falló `{cmd[0]} {cmd[1]}` (código {r.returncode})")
            if cmd[0] == "gh" and texto.startswith("https://"):
                url = texto.splitlines()[-1]
        return url
