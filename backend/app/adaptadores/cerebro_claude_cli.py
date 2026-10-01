"""Adaptador que delega en el CLI de Claude Code ya logueado en esta máquina
(`claude -p`), en vez de la API de Anthropic con una key propia.

Pensado solo para desarrollo local: corre contra el cupo del plan de Claude
Code (sesión de 5 horas, cupo semanal), no contra saldo de la API, así que no
sirve donde no haya una sesión de Claude Code logueada — un backend
desplegado (Render, etc.) no la tiene. Ver la advertencia de
`config.advertencias()` y el README para el detalle de esta decisión.

Usa `subprocess.Popen` en un hilo (`asyncio.to_thread`) en vez de
`asyncio.create_subprocess_exec`: en Windows, cuando uvicorn corre con
--reload, el proceso del servidor queda con un `SelectorEventLoop`, que no
soporta subprocesos asíncronos (`NotImplementedError` en
`_make_subprocess_transport`) — solo `ProactorEventLoop` los soporta. La
versión síncrona en un hilo no depende del tipo de loop.

Al vencer el timeout, matamos el ÁRBOL de procesos entero (`taskkill /T` en
Windows, el grupo de proceso en POSIX) — no alcanza con matar el proceso hijo
inmediato. `claude.CMD` es un wrapper de cmd.exe que lanza un `node.exe`
propio; `Popen.kill()` (y el timeout de `subprocess.run`) solo mata al
wrapper, y la limpieza se queda esperando a que el `node.exe` huérfano
termine solo — medido en la práctica, eso puede tardar 5-10x más que el
timeout configurado, y en el caso reportado por un usuario, más de 40 minutos
en vez de los 120s configurados. Confirmado con `subprocess.run(timeout=10)`
tardando ~98s en volver.

El prompt se manda por STDIN, no como argumento de `-p`: Windows tiene un
límite de longitud de línea de comandos (~32K caracteres, pero en la práctica
bastante menos vía CreateProcess con un `.CMD`), y el panel de asistente
(ver agents/asistente_codigo.py) mete el archivo generado completo dentro del
prompt para pedir una corrección — con archivos de un par de cientos de
líneas eso ya lo supera. El CLI, sin un prompt posicional después de `-p`,
lee del stdin — confirmado en vivo. Sin este cambio, `claude` fallaba con
"La línea de comandos es demasiado larga" (código de salida 1), y como eso
cae al respaldo igual que cualquier otro fallo, el efecto visible era mucho
peor: el endpoint reportaba "aplicado: true" sin haber cambiado una sola
línea, porque el respaldo de una corrección es el código actual sin tocar.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import subprocess
import sys
import tempfile

log = logging.getLogger(__name__)


def _lanzar(argumentos: list[str], *, cwd: str | None = None) -> subprocess.Popen[bytes]:
    """En un grupo/sesión de proceso propia para poder matar el árbol entero
    después — sin esto, matar solo el proceso devuelto no mata a sus hijos.

    `stdin=PIPE` siempre: `pensar()` manda el prompt por ahí (ver el docstring
    del módulo), y `cuenta_claude_cli()` no escribe nada — un stdin de pipe
    sin input simplemente se cierra vacío en `communicate()`, sin efecto.
    """
    if sys.platform == "win32":
        return subprocess.Popen(
            argumentos,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        argumentos,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        start_new_session=True,
    )


def _matar_arbol(proceso: subprocess.Popen[bytes]) -> None:
    """Mata al proceso y a todo lo que haya lanzado — `claude.CMD` es un
    wrapper de cmd.exe que a su vez lanza su propio node.exe; matar solo el
    wrapper deja ese node.exe corriendo huérfano, sin nada que lo pare.
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proceso.pid)],
            capture_output=True,
        )
    else:
        import os
        import signal

        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(proceso.pid), signal.SIGKILL)

    with contextlib.suppress(Exception):
        proceso.communicate(timeout=5)


# Reemplaza el prompt de sistema de Claude Code (que lo enmarca como "asistente
# de CLI consciente del repo") por uno de completado de texto puro. Sin esto,
# el CLI responde de forma conversacional ("esto ya existe, mirá...") en vez
# de devolver solo lo que pide la instrucción — rompe el contrato de
# Cerebro.pensar(), que espera texto plano, no una respuesta de chat.
_PROMPT_SISTEMA = (
    "Sos un motor de generación de texto. Devolvés exactamente lo que se te "
    "pide, sin agregar explicaciones, saludos, ni comentarios sobre el "
    "pedido. No sos un asistente conversacional."
)


class CerebroClaudeCLI:
    """Si el binario no está instalado, la sesión no está logueada, se cuelga
    más de lo esperado, o el proceso falla, cae al respaldo determinista —
    igual que CerebroAnthropic: un agente sin CLI disponible debe degradar,
    no explotar.
    """

    nombre = "claude-cli"

    def __init__(self, comando: str = "claude", timeout_s: float = 120.0) -> None:
        self._comando = comando
        self._timeout_s = timeout_s

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        prompt = f"{instruccion}\n\n<contexto>\n{contexto}\n</contexto>"
        # En Windows, los CLI de npm son shims .cmd — CreateProcess no los
        # ejecuta por nombre pelado sin pasar por una shell, pero sí acepta la
        # ruta completa que resuelve shutil.which(). En POSIX esto no cambia
        # nada (ya devuelve una ruta ejecutable directa).
        comando = shutil.which(self._comando) or self._comando
        argumentos = [
            comando,
            "-p",  # sin prompt posicional acá: se manda por stdin (ver arriba)
            "--output-format",
            "text",
            "--tools",
            "",  # sin herramientas: el prompt ya trae todo el contexto, esto
            # tiene que ser una generación de texto pura, no un agente que
            # explora o edita el repo.
            "--permission-prompts",
            "none",
            "--no-session-persistence",
            "--safe-mode",  # sin CLAUDE.md, plugins, hooks ni skills del repo
            "--system-prompt",
            _PROMPT_SISTEMA,
        ]
        try:
            # Un cwd neutral (no el repo) evita que el CLI descubra CLAUDE.md
            # o el estado de git y quede con el mismo contexto que
            # Cerebro.pensar() nunca prometió que tendría.
            proceso = await asyncio.to_thread(_lanzar, argumentos, cwd=tempfile.gettempdir())
        except OSError as e:
            log.warning("Cerebro Claude CLI falló (%s); se usa el respaldo", e)
            return respaldo

        try:
            salida, error = await asyncio.to_thread(
                proceso.communicate, prompt.encode("utf-8"), timeout=self._timeout_s
            )
            returncode = proceso.returncode
        except subprocess.TimeoutExpired:
            await asyncio.to_thread(_matar_arbol, proceso)
            log.warning(
                "Cerebro Claude CLI no respondió en %ss; se usa el respaldo", self._timeout_s
            )
            return respaldo

        if returncode != 0:
            log.warning(
                "Cerebro Claude CLI terminó con código %s (%s); se usa el respaldo",
                returncode,
                error.decode(errors="replace").strip()[:200],
            )
            return respaldo

        texto = salida.decode(errors="replace").strip()
        return texto or respaldo


async def cuenta_claude_cli(comando: str = "claude", timeout_s: float = 10.0) -> str | None:
    """Corre `claude auth status --json` y devuelve el email logueado.

    Quien tiene varias cuentas de Claude iniciadas en distintas terminales de
    la misma máquina necesita poder confirmar cuál es la que van a gastar las
    corridas — esto es solo para mostrarlo en Configuración, no participa de
    `pensar()`. Devuelve None ante cualquier problema (CLI ausente, no
    logueado, salida inesperada): es informativo, nunca debe tumbar nada.
    """
    ruta = shutil.which(comando) or comando
    try:
        proceso = await asyncio.to_thread(_lanzar, [ruta, "auth", "status", "--json"])
    except OSError as e:
        log.warning("No se pudo consultar la cuenta de Claude CLI (%s)", e)
        return None

    try:
        salida, _ = await asyncio.to_thread(proceso.communicate, timeout=timeout_s)
        returncode = proceso.returncode
    except subprocess.TimeoutExpired:
        await asyncio.to_thread(_matar_arbol, proceso)
        log.warning("Cerebro Claude CLI (auth status) no respondió en %ss", timeout_s)
        return None

    if returncode != 0:
        return None

    try:
        datos = json.loads(salida.decode(errors="replace"))
    except json.JSONDecodeError:
        return None

    email = datos.get("email")
    return email if isinstance(email, str) and email else None
