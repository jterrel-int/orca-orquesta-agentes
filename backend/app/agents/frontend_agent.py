"""Agente 2: genera la UI de Next.js que consume el API del backend, según el caso de uso."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..adaptadores.fabricas import construir_cerebro
from ..config import config
from ..dominio.puertos import Cerebro
from .base import Agente, ContextoCorrida
from .casos_de_uso import destino_frontend, resolver_caso


class FrontendAgent(Agente):
    name = "frontend"

    def __init__(self, cerebro: Cerebro | None = None) -> None:
        self._cerebro = cerebro or construir_cerebro()

    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        caso_id = ctx.datos.get("caso_de_uso")
        definicion = resolver_caso(caso_id)
        es_caso_nuevo = caso_id not in (None, "items")

        endpoints = ctx.datos.get("endpoints", [])
        if not endpoints:
            # No es un fallo: el frontend puede construirse contra el contrato
            # aunque el backend todavía no haya corrido.
            await self.log(ctx, "Sin endpoints del backend en el contexto; se usa el contrato base")

        destino = destino_frontend(caso_id)
        destino.mkdir(parents=True, exist_ok=True)

        await self.log(
            ctx, f"Construyendo UI contra {len(endpoints) or len(definicion.rutas)} endpoints"
        )
        await asyncio.sleep(config.duracion_paso_demo_s if es_caso_nuevo else 0.4)

        for paso in definicion.pasos_extra_frontend:
            await self.log(ctx, paso)
            await asyncio.sleep(config.duracion_paso_demo_s)

        await self.log(ctx, definicion.mensaje_generando_frontend)
        codigo = await self._cerebro.pensar(
            definicion.instruccion_frontend,
            contexto="Endpoints disponibles:\n" + "\n".join(endpoints),
            respaldo=definicion.respaldo_frontend,
        )
        codigo = _limpiar_cercas(codigo)

        if "export default" not in codigo:
            await self.log(
                ctx, "El componente generado no exporta por defecto; se usa la plantilla"
            )
            codigo = definicion.respaldo_frontend

        archivo = destino / definicion.archivo_frontend
        archivo.write_text(codigo, encoding="utf-8")
        await asyncio.sleep(config.duracion_paso_demo_s if es_caso_nuevo else 0.3)

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
