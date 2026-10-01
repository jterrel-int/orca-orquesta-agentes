"""Adaptadores SQLite de la fábrica. Lo que importa: la bitácora encadena
bien, y la base misma rechaza modificarla o borrarla.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.adaptadores.persistencia_sqlalchemy as persistencia
from app.adaptadores.ejecutor_pruebas import EjecutorLocal
from app.adaptadores.persistencia_fabrica import (
    BitacoraSQLAlchemy,
    RepositorioEncargosSQLAlchemy,
    RepositorioMetricasSQLAlchemy,
    tablas_existentes,
)
from app.dominio.fabrica import Encargo, Especificacion, MetricaEtapa, primer_registro_roto


@pytest.fixture
async def sesiones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    motor = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    fabrica = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(persistencia, "motor", motor)
    monkeypatch.setattr(persistencia, "FabricaSesion", fabrica)
    await persistencia.crear_tablas()
    yield fabrica
    await motor.dispose()


async def test_bitacora_encadena_y_se_verifica(sesiones: async_sessionmaker[AsyncSession]) -> None:
    bitacora = BitacoraSQLAlchemy(sesiones)
    r1 = await bitacora.registrar("a", "implementador", "archivos_escritos", {"n": 1})
    r2 = await bitacora.registrar("b", "revisor", "revision", {"ok": True})
    await bitacora.registrar("a", "verificador", "verificacion", {"ok": True})

    assert r2.hash_previo == r1.hash
    todos = await bitacora.listar()
    assert [r.secuencia for r in todos] == [1, 2, 3]
    assert primer_registro_roto(todos) is None
    assert [r.accion for r in await bitacora.listar("a")] == ["archivos_escritos", "verificacion"]


async def test_la_base_rechaza_modificar_o_borrar_la_bitacora(
    sesiones: async_sessionmaker[AsyncSession],
) -> None:
    await BitacoraSQLAlchemy(sesiones).registrar("a", "revisor", "revision", {"ok": False})
    async with sesiones() as sesion:
        with pytest.raises(DBAPIError, match="inmutable"):
            await sesion.execute(text("UPDATE fabrica_bitacora SET evidencia = '{\"ok\": true}'"))
        await sesion.rollback()
        with pytest.raises(DBAPIError, match="inmutable"):
            await sesion.execute(text("DELETE FROM fabrica_bitacora"))


async def test_encargos_y_metricas_ida_y_vuelta(sesiones: async_sessionmaker[AsyncSession]) -> None:
    repo = RepositorioEncargosSQLAlchemy(sesiones)
    encargo = Encargo(
        id="abc",
        pedido="p",
        especificaciones=[Especificacion("S1", "t", "d", archivos=["src/x.py"])],
    )
    await repo.guardar(encargo)
    encargo.estado = "terminado"
    await repo.guardar(encargo)
    assert await repo.obtener("abc") == encargo
    assert [e.id for e in await repo.listar()] == ["abc"]

    metricas = RepositorioMetricasSQLAlchemy(sesiones)
    await metricas.registrar(
        MetricaEtapa("abc", "revision", "revisor", "aprobado", 1.5, costo_usd=None, modelo="x")
    )
    [m] = await metricas.listar("abc")
    assert m.costo_usd is None and m.modelo == "x" and m.etapa == "revision"


async def test_tablas_existentes_ignora_las_de_la_fabrica(
    sesiones: async_sessionmaker[AsyncSession],
) -> None:
    # Una tabla "legada" cualquiera, como la que tendría una base existente.
    async with sesiones() as sesion:
        await sesion.execute(text("CREATE TABLE clientes (id INTEGER PRIMARY KEY)"))
        await sesion.commit()
    tablas = await tablas_existentes(sesiones)
    assert "clientes" in tablas
    assert not any(t.startswith("fabrica_") for t in tablas)


async def test_ejecutor_local_no_filtra_secretos_y_respeta_la_lista(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secreta")
    ejecutor = EjecutorLocal()
    r = await ejecutor.ejecutar(
        str(tmp_path),
        ["python", "-c", "import os; print(os.environ.get('ANTHROPIC_API_KEY', 'ausente'))"],
        30,
    )
    assert r.codigo_salida == 0
    assert "ausente" in r.salida and "sk-secreta" not in r.salida

    with pytest.raises(ValueError, match="no permitido"):
        await ejecutor.ejecutar(str(tmp_path), ["rm", "-rf", "/"], 5)
