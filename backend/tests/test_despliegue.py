"""DespliegueVercel: transmite el stdout línea por línea y extrae la URL de
producción. Simula el subproceso — no depende de tener el CLI de Vercel
instalado ni de una sesión real.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.adaptadores.despliegue_vercel import DespliegueVercel
from app.dominio.errores import DespliegueFallido


async def _lineas_async(lineas: list[str]) -> AsyncIterator[bytes]:
    for linea in lineas:
        yield f"{linea}\n".encode()


class ProcesoFalsoReal:
    """Doble de asyncio.subprocess.Process con lo mínimo que usa DespliegueVercel."""

    def __init__(self, lineas: list[str], codigo: int) -> None:
        self.stdout = _lineas_async(lineas)
        self._codigo = codigo

    async def wait(self) -> int:
        return self._codigo

    def kill(self) -> None:  # pragma: no cover - solo se usa si hay timeout
        pass


@pytest.fixture
def cwd_valido(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from app.config import config

    monkeypatch.setattr(config, "vercel_cwd", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/vercel")
    return tmp_path


async def test_extrae_la_url_de_produccion(cwd_valido, monkeypatch: pytest.MonkeyPatch) -> None:
    lineas = [
        "Vercel CLI 37.0.0",
        "🔍  Inspect: https://vercel.com/team/proyecto/abc123",
        "✅  Production: https://orquesta-demo.vercel.app [3s]",
    ]
    proceso = ProcesoFalsoReal(lineas, codigo=0)

    async def crear_subproceso_falso(*args, **kwargs):
        return proceso

    monkeypatch.setattr(asyncio, "create_subprocess_exec", crear_subproceso_falso)

    recibidas: list[str] = []

    async def on_linea(texto: str) -> None:
        recibidas.append(texto)

    url = await DespliegueVercel().ejecutar(on_linea)

    assert url == "https://vercel.com/team/proyecto/abc123"
    assert recibidas[1:] == lineas  # la primera línea es el "Ejecutando: ..."


async def test_codigo_de_salida_no_cero_lanza_desplieguefallido(
    cwd_valido, monkeypatch: pytest.MonkeyPatch
) -> None:
    proceso = ProcesoFalsoReal(["Error: algo salió mal"], codigo=1)

    async def crear_subproceso_falso(*args, **kwargs):
        return proceso

    monkeypatch.setattr(asyncio, "create_subprocess_exec", crear_subproceso_falso)

    with pytest.raises(DespliegueFallido, match="código 1"):
        await DespliegueVercel().ejecutar(lambda _: asyncio.sleep(0))


async def test_sin_cli_de_vercel_lanza_desplieguefallido(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import config

    monkeypatch.setattr(config, "vercel_cwd", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(DespliegueFallido, match="CLI de Vercel"):
        await DespliegueVercel().ejecutar(lambda _: asyncio.sleep(0))
