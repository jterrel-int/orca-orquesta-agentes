"""CerebroClaudeCLI.pensar(): corre `claude -p` como subproceso y cae al
respaldo determinista si el binario falta, tarda demasiado, o termina con
error — mismo criterio que CerebroAnthropic con la API real.

Mockea `cerebro_claude_cli._lanzar` (que envuelve `subprocess.Popen`) y
`_matar_arbol`, no `subprocess.run` — desde que se descubrió que matar solo el
proceso `claude.CMD` no mata al `node.exe` que lanza por debajo (ver el
docstring del módulo), `pensar()` usa Popen + un kill de árbol completo al
vencer el timeout, no `subprocess.run(timeout=...)`.
"""

from __future__ import annotations

import subprocess

import pytest

from app.adaptadores import cerebro_claude_cli as modulo
from app.adaptadores.cerebro_claude_cli import CerebroClaudeCLI, cuenta_claude_cli


class _ProcesoFalso:
    """Doble de subprocess.Popen: primera llamada a communicate() puede
    colgarse (TimeoutExpired), igual que el proceso real; la segunda (la que
    hace _matar_arbol para drenar) devuelve normal.
    """

    def __init__(
        self,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        agota_tiempo: bool = False,
    ) -> None:
        self.pid = 4242
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._agota_tiempo = agota_tiempo
        self.llamadas = 0
        self.entradas: list[bytes | None] = []

    def communicate(
        self, input: bytes | None = None, timeout: float | None = None
    ) -> tuple[bytes, bytes]:
        self.llamadas += 1
        self.entradas.append(input)
        if self._agota_tiempo and self.llamadas == 1:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout or 0)
        return self._stdout, self._stderr


@pytest.fixture(autouse=True)
def _sin_matar_procesos_reales(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """_matar_arbol() de verdad llama a taskkill/os.killpg — en los tests
    alcanza con confirmar que se llamó, nunca tocar procesos reales.
    """
    llamados: list[object] = []
    monkeypatch.setattr(modulo, "_matar_arbol", lambda proceso: llamados.append(proceso))
    return llamados


async def test_pensar_devuelve_la_salida_del_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    llamados_lanzar: list[list[object]] = []
    proceso_falso = _ProcesoFalso(stdout=b"codigo generado\n")

    # shutil.which() resuelve el shim real de la plataforma (p. ej. un .cmd en
    # Windows); acá lo fijamos para que el test no dependa de qué haya instalado.
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/claude")

    def _lanzar_falso(argumentos: list[object], **kwargs: object) -> _ProcesoFalso:
        llamados_lanzar.append(argumentos)
        return proceso_falso

    monkeypatch.setattr(modulo, "_lanzar", _lanzar_falso)

    cerebro = CerebroClaudeCLI("claude", timeout_s=5)
    texto = await cerebro.pensar("instrucción", contexto="ctx", respaldo="respaldo")

    assert texto == "codigo generado"
    assert llamados_lanzar[0][0] == "/usr/local/bin/claude"
    assert "-p" in llamados_lanzar[0]
    # El prompt va por stdin, no como argumento — un archivo largo en el
    # prompt (ver agents/asistente_codigo.py) supera el límite de longitud de
    # línea de comandos de Windows si va en argv.
    assert not any("instrucción" in str(a) for a in llamados_lanzar[0])
    assert proceso_falso.entradas == ["instrucción\n\n<contexto>\nctx\n</contexto>".encode()]


async def test_pensar_cae_al_respaldo_si_el_binario_no_existe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _falla(*args: object, **kwargs: object) -> _ProcesoFalso:
        raise FileNotFoundError("claude: no encontrado")

    monkeypatch.setattr(modulo, "_lanzar", _falla)

    cerebro = CerebroClaudeCLI("claude", timeout_s=5)
    texto = await cerebro.pensar("instrucción", respaldo="respaldo")

    assert texto == "respaldo"


async def test_pensar_cae_al_respaldo_si_termina_con_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        modulo, "_lanzar", lambda *a, **k: _ProcesoFalso(stderr=b"boom", returncode=1)
    )

    cerebro = CerebroClaudeCLI("claude", timeout_s=5)
    texto = await cerebro.pensar("instrucción", respaldo="respaldo")

    assert texto == "respaldo"


async def test_pensar_mata_el_arbol_si_se_cuelga(
    monkeypatch: pytest.MonkeyPatch, _sin_matar_procesos_reales: list[object]
) -> None:
    proceso_falso = _ProcesoFalso(agota_tiempo=True)
    monkeypatch.setattr(modulo, "_lanzar", lambda *a, **k: proceso_falso)

    cerebro = CerebroClaudeCLI("claude", timeout_s=0.01)
    texto = await cerebro.pensar("instrucción", respaldo="respaldo")

    assert texto == "respaldo"
    # Lo importante: mató el árbol completo, no confió en que el timeout de
    # communicate() por sí solo hubiera limpiado el proceso huérfano.
    assert _sin_matar_procesos_reales == [proceso_falso]


# --- cuenta_claude_cli(): qué cuenta de Claude va a gastar las corridas ---


async def test_cuenta_claude_cli_devuelve_el_email(monkeypatch: pytest.MonkeyPatch) -> None:
    salida = b'{"loggedIn": true, "email": "vos@ejemplo.com", "subscriptionType": "pro"}'
    monkeypatch.setattr(modulo, "_lanzar", lambda *a, **k: _ProcesoFalso(stdout=salida))

    assert await cuenta_claude_cli("claude") == "vos@ejemplo.com"


async def test_cuenta_claude_cli_none_si_el_binario_no_existe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _falla(*args: object, **kwargs: object) -> _ProcesoFalso:
        raise FileNotFoundError("claude: no encontrado")

    monkeypatch.setattr(modulo, "_lanzar", _falla)

    assert await cuenta_claude_cli("claude") is None


async def test_cuenta_claude_cli_none_si_no_esta_logueado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        modulo, "_lanzar", lambda *a, **k: _ProcesoFalso(stderr=b"no autenticado", returncode=1)
    )

    assert await cuenta_claude_cli("claude") is None


async def test_cuenta_claude_cli_none_si_la_salida_no_es_json_valido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(modulo, "_lanzar", lambda *a, **k: _ProcesoFalso(stdout=b"no es json"))

    assert await cuenta_claude_cli("claude") is None


async def test_cuenta_claude_cli_mata_el_arbol_si_se_cuelga(
    monkeypatch: pytest.MonkeyPatch, _sin_matar_procesos_reales: list[object]
) -> None:
    proceso_falso = _ProcesoFalso(agota_tiempo=True)
    monkeypatch.setattr(modulo, "_lanzar", lambda *a, **k: proceso_falso)

    assert await cuenta_claude_cli("claude", timeout_s=0.01) is None
    assert _sin_matar_procesos_reales == [proceso_falso]
