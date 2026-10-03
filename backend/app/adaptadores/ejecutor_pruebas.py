"""Adaptadores del puerto EjecutorPruebas: dónde corre el código que generó
un agente para verificarlo.

- EjecutorLocal: subproceso en esta máquina. Rápido y sin dependencias, pero
  el código generado corre con los permisos del backend. Se le quitan al
  entorno las claves (*_API_KEY, *TOKEN*, *SECRET*) para que un `print(os.environ)`
  generado no las filtre a la bitácora.
- EjecutorDocker: contenedor sin red, raíz de solo lectura, sin capacidades
  y con límites de memoria/CPU/procesos. Es lo recomendable con un cerebro
  real (ver config.fabrica_sandbox).

Los dos aceptan solo una lista corta de ejecutables. Un agente no elige
comandos arbitrarios: el Revisor y el Verificador piden los suyos, fijos.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from ..dominio.fabrica import ResultadoComando

EJECUTABLES_PERMITIDOS = frozenset({"python", "npx"})
# Por nombre: claves, tokens, contraseñas, credenciales y URLs de bases de
# datos (que suelen llevar usuario y contraseña adentro).
_SECRETO = re.compile(
    r"(KEY|TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|COOKIE|SESSION|DATABASE_URL|DSN|PRIVATE)",
    re.IGNORECASE,
)
_MAX_SALIDA = 6000


def _recortar(texto: str) -> str:
    if len(texto) <= _MAX_SALIDA:
        return texto
    mitad = _MAX_SALIDA // 2
    return (
        f"{texto[:mitad]}\n… [{len(texto) - _MAX_SALIDA} caracteres omitidos] …\n{texto[-mitad:]}"
    )


def _entorno_sin_secretos() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not _SECRETO.search(k)}


def _validar(comando: list[str]) -> None:
    if not comando or comando[0] not in EJECUTABLES_PERMITIDOS:
        raise ValueError(f"Comando no permitido por la política del harness: {comando[:1]}")


def _correr_bloqueante(
    argv: list[str], cwd: str | None, env: dict[str, str] | None, timeout_s: float
) -> tuple[int, str]:
    try:
        r = subprocess.run(  # noqa: S603 — argv validado por _validar
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as e:
        # 127: la convención de shell para "comando no encontrado". El
        # Diagnosticador la reconoce como un problema del harness.
        return 127, f"No se encontró el ejecutable: {e}"
    except subprocess.TimeoutExpired:
        return 124, f"Se superó el tiempo límite de {timeout_s:.0f}s"
    return r.returncode, r.stdout.decode("utf-8", errors="replace") if r.stdout else ""


async def _correr(
    argv: list[str], cwd: str | None, env: dict[str, str] | None, timeout_s: float
) -> tuple[int, str, float]:
    """subprocess en un hilo y no asyncio.create_subprocess_exec: en Windows,
    uvicorn --reload corre con un SelectorEventLoop que no soporta
    subprocesos asíncronos (mismo motivo que en cerebro_claude_cli.py).
    """
    inicio = time.perf_counter()
    codigo, salida = await asyncio.to_thread(_correr_bloqueante, argv, cwd, env, timeout_s)
    return codigo, _recortar(salida), time.perf_counter() - inicio


class EjecutorLocal:
    nombre = "local"

    async def ejecutar(
        self, directorio: str, comando: list[str], timeout_s: float
    ) -> ResultadoComando:
        _validar(comando)
        # "python" es el mismo intérprete del backend: así pytest está
        # disponible sin depender de qué haya en el PATH.
        argv = [sys.executable, *comando[1:]] if comando[0] == "python" else comando
        codigo, salida, duracion = await _correr(
            argv, directorio, _entorno_sin_secretos(), timeout_s
        )
        return ResultadoComando(comando, codigo, salida, round(duracion, 2), self.nombre)


class EjecutorDocker:
    nombre = "docker"

    def __init__(self, imagen: str, *, red: str = "none") -> None:
        self._imagen = imagen
        self._red = red

    async def ejecutar(
        self, directorio: str, comando: list[str], timeout_s: float
    ) -> ResultadoComando:
        _validar(comando)
        montaje = str(Path(directorio).resolve())
        argv = [
            "docker", "run", "--rm",
            "--network", self._red,
            "--read-only", "--tmpfs", "/tmp",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "1g", "--cpus", "2", "--pids-limit", "256",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{montaje}:/trabajo", "-w", "/trabajo",
            self._imagen, *comando,
        ]  # fmt: skip
        codigo, salida, duracion = await _correr(argv, None, None, timeout_s)
        return ResultadoComando(comando, codigo, salida, round(duracion, 2), self.nombre)
