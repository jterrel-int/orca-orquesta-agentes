"""Implementador: construye todo lo que pide una especificación — código,
interfaz y pruebas unitarias — en el espacio de trabajo del encargo. No hay
roles separados de frontend y backend.

Lo que queda en la bitácora no es lo que el agente dice haber escrito: el
harness relee cada archivo del disco y registra su hash real.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ...dominio.fabrica import Especificacion, PoliticaFabrica, ruta_permitida, sha256_texto
from ...dominio.puertos import Cerebro
from .comun import LIMITE_CONTEXTO, Medidor, armar_contexto, extraer_json

_PYTEST_INI = "[pytest]\naddopts = -p no:cacheprovider\ntestpaths = tests\n"


@dataclass
class ResultadoImplementacion:
    escritos: list[dict[str, object]] = field(default_factory=list)
    denegados: list[str] = field(default_factory=list)
    origen: str = "plantilla"
    # Hay un cerebro real y aun así se usó la plantilla: no respondió a tiempo
    # o devolvió algo que no se pudo leer. No es un defecto del código ni de
    # la especificación, y reintentar igual suele fallar igual.
    cerebro_fallo: bool = False


def preparar_espacio(espacio: Path) -> None:
    """Andamiaje del harness, no del agente: igual en todos los encargos."""
    for carpeta in ("src", "tests"):
        (espacio / carpeta).mkdir(parents=True, exist_ok=True)
        (espacio / carpeta / "__init__.py").touch(exist_ok=True)
    ini = espacio / "pytest.ini"
    if not ini.exists():
        ini.write_text(_PYTEST_INI, encoding="utf-8")


def _modulo_fuente(espec: Especificacion) -> str | None:
    fuente = next((a for a in espec.archivos if a.startswith("src/") and a.endswith(".py")), None)
    return PurePosixPath(fuente).stem if fuente else None


def plantilla(espec: Especificacion, ruta: str) -> str:
    """Respaldo determinista por tipo de archivo. Funciona y está probado,
    aunque no implemente la lógica de negocio: es lo que produce el cerebro
    guionado para que el pipeline completo se pueda ver sin una API key.
    """
    ruta_p = PurePosixPath(ruta)
    modulo = _modulo_fuente(espec) or "modulo"
    funcion = f"ejecutar_{modulo}"
    titulo = espec.titulo.replace('"', "'")
    if ruta.startswith("src/") and ruta.endswith(".py"):
        nombre = f"ejecutar_{ruta_p.stem}"
        return (
            f'"""{espec.id}: {titulo}"""\n\n\n'
            f"def {nombre}(datos: dict | None = None) -> dict:\n"
            f'    """{titulo}"""\n'
            "    return {\n"
            f'        "especificacion": "{espec.id}",\n'
            '        "estado": "implementado",\n'
            '        "datos": dict(datos or {}),\n'
            "    }\n"
        )
    if ruta.startswith("tests/") and ruta.endswith(".py"):
        return (
            f"from src.{modulo} import {funcion}\n\n\n"
            f"def test_{funcion}_responde_implementado() -> None:\n"
            f"    resultado = {funcion}()\n"
            f'    assert resultado["especificacion"] == "{espec.id}"\n'
            '    assert resultado["estado"] == "implementado"\n\n\n'
            f"def test_{funcion}_conserva_los_datos() -> None:\n"
            f'    assert {funcion}({{"a": 1}})["datos"] == {{"a": 1}}\n'
        )
    if ruta.endswith(".spec.ts"):
        return (
            'import { expect, test } from "@playwright/test";\n\n'
            f'test("{titulo}", async ({{ page }}) => {{\n'
            '  await page.goto("/");\n'
            "  await expect(page).toHaveTitle(/.+/);\n"
            "});\n"
        )
    if ruta.endswith(".tsx"):
        return (
            f"export default function {ruta_p.stem.title().replace('_', '')}() {{\n"
            f"  return <section><h2>{titulo}</h2></section>;\n"
            "}\n"
        )
    if ruta.endswith(".py"):
        # Cualquier otro .py (p. ej. pruebas en e2e/): Python válido, o el
        # Revisor lo rechazaría por sintaxis y el rechazo parecería del código.
        return f'"""{espec.id}: {titulo} (pendiente)"""\n'
    if ruta.endswith(".html"):
        return (
            '<!doctype html>\n<html lang="es">\n<head><meta charset="utf-8">'
            f"<title>{titulo}</title></head>\n<body><h1>{titulo}</h1></body>\n</html>\n"
        )
    return f"{espec.id}: {titulo}\n"


def _instruccion() -> str:
    return (
        "Sos el Implementador de una fábrica de software. Escribí TODOS los archivos "
        "que pide la especificación: código, interfaz si corresponde y pruebas "
        "unitarias con pytest. El código Python va en src/ y las pruebas lo importan "
        "como `from src.modulo import funcion`. Cada función pública debe usarse en "
        "alguna prueba. Si hay un detalle_rechazo_previo, corregí exactamente ese error "
        "siguiendo el diagnóstico. Respetá el código_de_dependencias tal como está (mismos "
        "esquemas de tablas, nombres y firmas); si necesitás cambiarlo, hacelo de forma "
        "compatible con lo que ya existe. Respondé SOLO "
        'un objeto JSON: {"archivos": [{"ruta": "src/x.py", "contenido": "..."}]}.'
    )


class Implementador:
    name = "implementador"

    def __init__(self, cerebro: Cerebro, limite_contexto: int = LIMITE_CONTEXTO) -> None:
        self._cerebro = cerebro
        self._limite = limite_contexto

    async def implementar(
        self,
        espec: Especificacion,
        espacio: Path,
        politica: PoliticaFabrica,
        *,
        motivo_rechazo: str,
        medidor: Medidor,
        historial: list[dict[str, object]] | None = None,
        inventario: list[str] | None = None,
        detalle_rechazo: dict[str, object] | None = None,
        dependencias: dict[str, str] | None = None,
    ) -> ResultadoImplementacion:
        """`historial` es el resumen compacto de los intentos anteriores de
        esta misma especificación (motivo, causa y archivos de cada uno): el
        reintento arranca informado sin arrastrar las salidas completas.
        """
        preparar_espacio(espacio)
        actuales = {
            a: (espacio / a).read_text(encoding="utf-8")
            for a in espec.archivos
            if (espacio / a).is_file()
        }
        contexto = armar_contexto(
            {
                "especificacion": vars(espec),
                "archivos_actuales": actuales,
                "motivo_rechazo_previo": motivo_rechazo or None,
                # El error real (salida de las pruebas) y el diagnóstico: sin
                # esto el reintento solo ve "10 failed" y repite el mismo error.
                "detalle_rechazo_previo": detalle_rechazo,
                # El código de las especificaciones de las que depende esta:
                # esquemas de tablas, firmas y nombres que hay que respetar.
                "codigo_de_dependencias": dependencias or {},
                "intentos_previos": historial or [],
                # Todo lo que ya hay en el espacio (p. ej. lo heredado de la
                # versión anterior): para importarlo o extenderlo, no duplicarlo.
                "archivos_del_espacio": inventario or [],
            },
            self._limite,
            medidor,
        )
        respaldo = json.dumps(
            {"archivos": [{"ruta": a, "contenido": plantilla(espec, a)} for a in espec.archivos]},
            ensure_ascii=False,
        )
        crudo = await medidor.pensar(self._cerebro, _instruccion(), contexto, respaldo=respaldo)
        datos = extraer_json(crudo)
        origen = "plantilla" if crudo == respaldo else "cerebro"
        archivos = datos.get("archivos") if isinstance(datos, dict) else None
        if not isinstance(archivos, list) or not archivos:
            archivos, origen = json.loads(respaldo)["archivos"], "plantilla"

        resultado = ResultadoImplementacion(
            origen=origen,
            # El guionado siempre devuelve la plantilla: eso no es una falla.
            cerebro_fallo=origen == "plantilla" and medidor.modelo not in ("", "guionado"),
        )
        for archivo in archivos:
            if not isinstance(archivo, dict):
                continue
            ruta = str(archivo.get("ruta", "")).replace("\\", "/")
            if not ruta_permitida(ruta, politica):
                resultado.denegados.append(ruta)
                continue
            destino = espacio / ruta
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(str(archivo.get("contenido", "")), encoding="utf-8")
            # Se relee del disco: lo que se registra es lo que quedó escrito.
            en_disco = destino.read_text(encoding="utf-8")
            resultado.escritos.append(
                {"ruta": ruta, "sha256": sha256_texto(en_disco), "bytes": len(en_disco)}
            )
        return resultado
