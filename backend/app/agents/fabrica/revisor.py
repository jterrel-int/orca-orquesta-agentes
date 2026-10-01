"""Revisor: valida la implementación contra la especificación y corre las
pruebas unitarias.

Orden deliberado, de lo más barato y determinista a lo más caro:
validación cruzada contra la bitácora → archivos del contrato → sintaxis →
pytest → criterio del LLM. El LLM solo puede rechazar algo que las reglas
aprobaron; nunca aprobar algo que las reglas rechazaron.
"""

from __future__ import annotations

from pathlib import Path

from ...dominio.fabrica import Especificacion, Veredicto, sha256_texto
from ...dominio.puertos import Cerebro, EjecutorPruebas
from .comun import LIMITE_CONTEXTO, Medidor, armar_contexto, extraer_json

_COLA_SALIDA = 1500


def _cola(texto: str) -> str:
    return texto[-_COLA_SALIDA:]


class Revisor:
    name = "revisor"

    def __init__(
        self,
        cerebro: Cerebro,
        ejecutor: EjecutorPruebas,
        timeout_s: float,
        limite_contexto: int = LIMITE_CONTEXTO,
    ) -> None:
        self._cerebro = cerebro
        self._limite = limite_contexto
        self._ejecutor = ejecutor
        self._timeout_s = timeout_s

    async def revisar(
        self,
        espec: Especificacion,
        espacio: Path,
        escritos: list[dict[str, object]],
        *,
        medidor: Medidor,
    ) -> Veredicto:
        # 1. Validación cruzada: lo que el Implementador registró, ¿es lo que hay?
        for e in escritos:
            ruta = str(e["ruta"])
            archivo = espacio / ruta
            if not archivo.is_file():
                return Veredicto(
                    False, f"Validación cruzada: {ruta} está en la bitácora pero no en disco"
                )
            if sha256_texto(archivo.read_text(encoding="utf-8")) != e["sha256"]:
                return Veredicto(
                    False,
                    f"Validación cruzada: {ruta} cambió después de registrarse en la bitácora",
                )

        # 2. El contrato de la especificación.
        faltan = [a for a in espec.archivos if not (espacio / a).is_file()]
        if faltan:
            return Veredicto(False, f"Faltan archivos de la especificación: {', '.join(faltan)}")

        # 3. Sintaxis.
        for a in espec.archivos:
            if a.endswith(".py"):
                try:
                    compile((espacio / a).read_text(encoding="utf-8"), a, "exec")
                except SyntaxError as err:
                    return Veredicto(False, f"{a} no compila: {err}")

        # 4. Pruebas unitarias, de verdad.
        pruebas = [a for a in espec.archivos if a.startswith("tests/") and a.endswith(".py")]
        if not pruebas:
            return Veredicto(False, "Especificación: no declara pruebas unitarias en tests/")
        comando = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", *pruebas]
        r = await self._ejecutor.ejecutar(str(espacio), comando, self._timeout_s)
        evidencia: dict[str, object] = {
            "comando": " ".join(comando),
            "codigo_salida": r.codigo_salida,
            "duracion_s": r.duracion_s,
            "sandbox": r.sandbox,
            "salida": _cola(r.salida),
        }
        if r.codigo_salida != 0:
            ultima = r.salida.strip().splitlines()[-1] if r.salida.strip() else "sin salida"
            return Veredicto(
                False, f"Pruebas unitarias fallaron (código {r.codigo_salida}): {ultima}", evidencia
            )

        # 5. Criterio: ¿cumple lo que la especificación pide?
        contenido = {a: (espacio / a).read_text(encoding="utf-8") for a in espec.archivos}
        crudo = await medidor.pensar(
            self._cerebro,
            "Sos el Revisor de una fábrica de software. Las pruebas ya pasaron. "
            "Decidí si los archivos cumplen los criterios de aceptación de la "
            'especificación. Respondé SOLO JSON: {"aprobado": true|false, "motivo": "..."}.',
            armar_contexto(
                {"especificacion": vars(espec), "archivos": contenido}, self._limite, medidor
            ),
            respaldo='{"aprobado": true, "motivo": ""}',
        )
        datos = extraer_json(crudo)
        if isinstance(datos, dict) and datos.get("aprobado") is False:
            motivo = str(datos.get("motivo") or "No cumple los criterios de aceptación")
            return Veredicto(False, f"Criterios: {motivo}", evidencia)
        return Veredicto(True, "", evidencia)
