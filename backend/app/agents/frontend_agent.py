"""Agente 2: genera la UI de Next.js que consume el API del backend."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import config
from .base import Agente, ContextoCorrida
from .cerebros import Cerebro, construir_cerebro
from .plantillas import LISTA_ITEMS_TSX

INSTRUCCION = (
    "Escribe un componente cliente de React para Next.js App Router que liste, "
    "cree y elimine items consumiendo el helper @/lib/api. TypeScript, sin "
    "librerías externas, con estados de carga, error y vacío. "
    "Devuelve solo el código, sin explicación ni cercas de markdown."
)


class FrontendAgent(Agente):
    name = "frontend"

    def __init__(self, cerebro: Cerebro | None = None) -> None:
        self._cerebro = cerebro or construir_cerebro()

    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        endpoints = ctx.datos.get("endpoints", [])
        if not endpoints:
            # No es un fallo: el frontend puede construirse contra el contrato
            # aunque el backend todavía no haya corrido.
            await self.log(ctx, "Sin endpoints del backend en el contexto; se usa el contrato base")

        destino = Path(config.dir_generado_frontend)
        destino.mkdir(parents=True, exist_ok=True)

        await self.log(ctx, f"Construyendo UI contra {len(endpoints) or 5} endpoints")
        await asyncio.sleep(0.4)

        await self.log(ctx, "Generando el componente ListaItems")
        codigo = await self._cerebro.pensar(
            INSTRUCCION,
            contexto="Endpoints disponibles:\n" + "\n".join(endpoints),
            respaldo=LISTA_ITEMS_TSX,
        )
        codigo = _limpiar_cercas(codigo)

        if "export default" not in codigo:
            await self.log(ctx, "El componente generado no exporta por defecto; se usa la plantilla")
            codigo = LISTA_ITEMS_TSX

        archivo = destino / "ListaItems.tsx"
        archivo.write_text(codigo, encoding="utf-8")
        await asyncio.sleep(0.3)

        ctx.datos["componente_generado"] = str(archivo)
        await self.log(ctx, "UI lista; Next.js la recarga en caliente")
        return [_relativa(archivo)]


def _limpiar_cercas(texto: str) -> str:
    lineas = texto.strip().splitlines()
    if lineas and lineas[0].startswith("```"):
        lineas = lineas[1:]
    if lineas and lineas[-1].startswith("```"):
        lineas = lineas[:-1]
    return "\n".join(lineas) + "\n"


def _relativa(p: Path) -> str:
    try:
        return str(p.relative_to(Path(config.vercel_cwd).parent))
    except ValueError:
        return str(p)
