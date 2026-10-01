"""Verificador: lo que el Revisor no mira.

- Caja blanca (siempre): cada función o clase pública del código de la
  especificación aparece en alguna de sus pruebas. Se lee el AST, no se le
  pregunta al LLM.
- Funcional (si la especificación tiene interfaz y FABRICA_E2E_ENABLED=true):
  Playwright con Chromium en un contenedor. Apagado, se informa "omitido" —
  nunca se da por aprobado algo que no corrió.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ...dominio.fabrica import Especificacion, Veredicto
from ...dominio.puertos import EjecutorPruebas

_CONFIG_PLAYWRIGHT = """import {{ defineConfig, devices }} from "@playwright/test";

export default defineConfig({{
  testDir: "./e2e",
  reporter: "line",
  use: {{ baseURL: "{url}" }},
  projects: [{{ name: "chromium", use: {{ ...devices["Desktop Chrome"] }} }}],
}});
"""


def simbolos_publicos(codigo: str) -> list[str]:
    arbol = ast.parse(codigo)
    return [
        n.name
        for n in arbol.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and not n.name.startswith("_")
    ]


class Verificador:
    name = "verificador"

    def __init__(
        self, ejecutor_e2e: EjecutorPruebas | None, url_base: str, timeout_s: float
    ) -> None:
        self._ejecutor_e2e = ejecutor_e2e
        self._url_base = url_base
        self._timeout_s = timeout_s

    async def verificar(self, espec: Especificacion, espacio: Path) -> Veredicto:
        pruebas = "\n".join(
            (espacio / a).read_text(encoding="utf-8")
            for a in espec.archivos
            if a.startswith("tests/") and (espacio / a).is_file()
        )
        cubiertos: list[str] = []
        for a in espec.archivos:
            if not (a.startswith("src/") and a.endswith(".py")):
                continue
            for simbolo in simbolos_publicos((espacio / a).read_text(encoding="utf-8")):
                if simbolo not in pruebas:
                    return Veredicto(
                        False,
                        f"Caja blanca: `{simbolo}` ({a}) no aparece en ninguna prueba",
                        {"cubiertos": cubiertos},
                    )
                cubiertos.append(simbolo)

        evidencia: dict[str, object] = {"caja_blanca": cubiertos}
        e2e = [a for a in espec.archivos if a.startswith("e2e/")]
        if not (espec.e2e and e2e):
            evidencia["e2e"] = "no aplica"
            return Veredicto(True, "", evidencia)
        if self._ejecutor_e2e is None:
            evidencia["e2e"] = "omitido: FABRICA_E2E_ENABLED=false"
            return Veredicto(True, "", evidencia)

        (espacio / "playwright.config.ts").write_text(
            _CONFIG_PLAYWRIGHT.format(url=self._url_base), encoding="utf-8"
        )
        comando = ["npx", "playwright", "test", *e2e]
        r = await self._ejecutor_e2e.ejecutar(str(espacio), comando, self._timeout_s)
        evidencia.update(
            {
                "e2e": "ejecutado",
                "comando": " ".join(comando),
                "codigo_salida": r.codigo_salida,
                "salida": r.salida[-1500:],
            }
        )
        if r.codigo_salida != 0:
            return Veredicto(
                False, f"Pruebas funcionales fallaron (código {r.codigo_salida})", evidencia
            )
        return Veredicto(True, "", evidencia)
