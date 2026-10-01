"""Iterar sobre una ejecución (nuevas versiones), reiniciar la línea y leer
lo que quedó en fabrica_espacios/.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fabrica_falsos import construir_lider

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.dominio.errores import AccionNoPermitida, EncargoNoEncontrado
from app.dominio.fabrica import ResultadoComando


class CerebroEspia(CerebroGuionado):
    """Guionado que guarda cada contexto recibido."""

    def __init__(self) -> None:
        self.contextos: list[str] = []

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        self.contextos.append(contexto)
        return respaldo

    async def pensar_medido(self, instruccion: str, contexto: str = "", *, respaldo: str = ""):  # type: ignore[no-untyped-def]
        self.contextos.append(contexto)
        return await super().pensar_medido(instruccion, contexto, respaldo=respaldo)


async def test_una_nueva_version_hereda_los_archivos_y_el_contexto(tmp_path: Path) -> None:
    espia = CerebroEspia()
    lider, _, bitacora, *_ = construir_lider(tmp_path, cerebro=espia)

    v1 = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(v1.id)
    archivos_v1 = {a["ruta"] for a in await lider.archivos(v1.id)}
    assert "src/calcular_el_total_de_un_carr.py" in archivos_v1

    v2 = await lider.crear("Aplicar un cupón de descuento sobre el total", base_id=v1.id)
    await lider.esperar(v2.id)
    v2 = await lider.obtener(v2.id)

    assert (v2.version, v2.padre_id, v2.raiz_id, v2.linaje) == (2, v1.id, v1.id, v1.id)
    assert v2.estado == "terminado", v2.motivo
    archivos_v2 = {a["ruta"] for a in await lider.archivos(v2.id)}
    assert archivos_v1 <= archivos_v2  # lo heredado sigue ahí
    assert any("cupon" in a for a in archivos_v2)  # y se sumó lo nuevo

    # La línea de base heredada queda sellada en la bitácora.
    recibido = next(
        r for r in bitacora.registros if r.encargo_id == v2.id and r.accion == "encargo_recibido"
    )
    heredados = {a["ruta"] for a in recibido.evidencia["archivos_heredados"]}
    assert heredados == archivos_v1
    assert all(len(a["sha256"]) == 64 for a in recibido.evidencia["archivos_heredados"])

    # El Especificador de la v2 recibió la versión anterior como contexto.
    contexto_v2 = next(
        json.loads(c) for c in reversed(espia.contextos) if '"version_base"' in c and "cupón" in c
    )
    base: dict[str, Any] = contexto_v2["version_base"]
    assert base["pedido_anterior"] == "Calcular el total de un carrito con impuestos"
    assert "src/calcular_el_total_de_un_carr.py" in base["archivos_existentes"]


async def test_las_versiones_se_numeran_dentro_del_linaje(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path)
    v1 = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(v1.id)
    v2 = await lider.crear("Aplicar un cupón de descuento", base_id=v1.id)
    await lider.esperar(v2.id)
    # Ramificar desde la v1 otra vez: es la v3 del mismo producto, no otra v2.
    v3 = await lider.crear("Exportar el carrito a CSV", base_id=v1.id)
    await lider.esperar(v3.id)
    assert ((await lider.obtener(v3.id)).version, (await lider.obtener(v3.id)).raiz_id) == (
        3,
        v1.id,
    )

    with pytest.raises(EncargoNoEncontrado):
        await lider.crear("x y z w", base_id="no-existe")


class EjecutorQueNoTermina:
    async def ejecutar(
        self, directorio: str, comando: list[str], timeout_s: float
    ) -> ResultadoComando:
        await asyncio.sleep(60)
        raise AssertionError("no debería llegar acá")


async def test_reiniciar_la_linea_detiene_y_archiva_sin_borrar(tmp_path: Path) -> None:
    lider, repo, bitacora, *_ = construir_lider(
        tmp_path, ejecutor=EjecutorQueNoTermina(), tablas=["items"]
    )
    en_pausa = await lider.crear("Agregar etiquetas de color a los items")
    await lider.esperar(en_pausa.id)
    corriendo = await lider.crear("Calcular el total de un carrito con impuestos")
    await asyncio.sleep(0.3)
    assert lider.corriendo(corriendo.id)

    resultado = await lider.reiniciar_linea()

    assert set(resultado["archivados"]) == {en_pausa.id, corriendo.id}
    assert resultado["detenidos"] == [corriendo.id]
    assert not lider.corriendo(corriendo.id)
    detenido = await lider.obtener(corriendo.id)
    assert detenido.estado == "interrumpido" and detenido.archivado_en is not None
    assert all(e.estado != "en_curso" for e in detenido.especificaciones)
    assert (await lider.obtener(en_pausa.id)).estado == "esperando_humano"  # conserva su estado
    assert len(repo.datos) == 2  # nada se borró
    assert bitacora.acciones().count("archivado") == 2

    # Un archivado no acepta respuestas: se reanuda o se itera desde Ejecuciones.
    pregunta = (await lider.obtener(en_pausa.id)).preguntas[0]
    with pytest.raises(AccionNoPermitida, match="archivado"):
        await lider.responder(en_pausa.id, pregunta.id, "Reutilizar")


async def test_reanudar_un_archivado_lo_devuelve_a_la_linea(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path, ejecutor=EjecutorQueNoTermina())
    encargo = await lider.crear("Calcular el total de un carrito con impuestos")
    await asyncio.sleep(0.3)
    await lider.reiniciar_linea()

    await lider.reanudar(encargo.id)
    assert (await lider.obtener(encargo.id)).archivado_en is None
    await lider.reiniciar_linea()  # para no dejar la tarea colgada


async def test_ejecuciones_cruza_carpetas_y_base(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path)
    encargo = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(encargo.id)
    huerfana = tmp_path / "espacios" / "abc12345"
    (huerfana / "src").mkdir(parents=True)
    (huerfana / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (huerfana / "__pycache__").mkdir()
    (huerfana / "__pycache__" / "x.pyc").write_bytes(b"...")

    por_id = {e.id: e for e in await lider.ejecuciones()}

    assert por_id[encargo.id].en_base and por_id[encargo.id].carpeta
    assert por_id[encargo.id].estado == "terminado"
    assert por_id[encargo.id].archivos > 0 and por_id[encargo.id].bytes > 0
    assert not por_id["abc12345"].en_base and por_id["abc12345"].archivos == 1  # sin caché


async def test_leer_archivo_no_sale_de_la_carpeta(tmp_path: Path) -> None:
    lider, *_ = construir_lider(tmp_path)
    encargo = await lider.crear("Calcular el total de un carrito con impuestos")
    await lider.esperar(encargo.id)
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")

    contenido = await lider.leer_archivo(encargo.id, "src/calcular_el_total_de_un_carr.py")
    assert "def ejecutar_" in contenido
    with pytest.raises(AccionNoPermitida):
        await lider.leer_archivo(encargo.id, "../../secreto.txt")
    with pytest.raises(EncargoNoEncontrado):
        await lider.archivos("..")


async def test_cargar_en_la_linea_un_archivado_que_espera_una_decision(tmp_path: Path) -> None:
    lider, _, bitacora, *_ = construir_lider(tmp_path, tablas=["items"])
    encargo = await lider.crear("Agregar etiquetas de color a los items")
    await lider.esperar(encargo.id)
    await lider.reiniciar_linea()

    restaurado = await lider.reanudar(encargo.id)

    assert restaurado.archivado_en is None
    assert restaurado.estado == "esperando_humano"  # sigue esperando, no se relanzó
    assert not lider.corriendo(encargo.id)
    assert "restaurado" in bitacora.acciones()
    # Ya se le puede responder.
    await lider.responder(encargo.id, restaurado.preguntas[0].id, "Reutilizar la tabla existente")
    await lider.esperar(encargo.id)
    assert (await lider.obtener(encargo.id)).estado == "terminado"
