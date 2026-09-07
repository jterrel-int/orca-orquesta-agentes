"""Agente 1: genera el modelo y los endpoints del backend según el caso de uso."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..adaptadores.fabricas import construir_cerebro
from ..config import config
from ..dominio.puertos import Cerebro
from .base import Agente, ContextoCorrida
from .casos_de_uso import destino_backend, resolver_caso


class BackendAgent(Agente):
    name = "backend"

    def __init__(self, cerebro: Cerebro | None = None) -> None:
        # `construir_cerebro()` es async (puede leer una credencial guardada
        # en SQLite), así que no se resuelve acá: se resuelve en `ejecutar`,
        # una vez por corrida, salvo que ya venga uno inyectado (tests).
        self._cerebro_dado = cerebro

    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        cerebro = self._cerebro_dado or await construir_cerebro()
        caso_id = ctx.datos.get("caso_de_uso")
        definicion = resolver_caso(caso_id)
        # "items" (o None) es el comportamiento histórico: pausas cortas y fijas.
        # Los tres casos nuevos usan una pausa configurable para que una corrida
        # completa se sienta como una demo real (ver duracion_paso_demo_s en
        # config.py) sin volver más lenta la suite de tests del caso Items.
        es_caso_nuevo = caso_id not in (None, "items")

        destino = destino_backend()
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "__init__.py").touch(exist_ok=True)

        await self.log(ctx, definicion.mensaje_modelo_backend)
        await asyncio.sleep(config.duracion_paso_demo_s if es_caso_nuevo else 0.4)

        for paso in definicion.pasos_extra_backend:
            await self.log(ctx, paso)
            await asyncio.sleep(config.duracion_paso_demo_s)

        await self.log(ctx, definicion.mensaje_generando_backend)
        codigo = await cerebro.pensar(
            definicion.instruccion_backend,
            contexto=definicion.contexto_backend,
            respaldo=definicion.respaldo_backend,
        )
        codigo = _limpiar_cercas(codigo)

        # Un LLM puede devolver algo que no compila. Verificar antes de escribir
        # es la diferencia entre un agente y un generador de texto.
        await self.log(ctx, "Verificando que el código generado compile")
        try:
            compile(codigo, "<generado>", "exec")
        except SyntaxError as e:
            await self.log(ctx, f"El código generado no compila ({e}); se usa la plantilla")
            codigo = definicion.respaldo_backend

        archivo = destino / definicion.archivo_backend
        archivo.write_text(codigo, encoding="utf-8")
        await asyncio.sleep(config.duracion_paso_demo_s if es_caso_nuevo else 0.3)

        rutas = list(definicion.rutas)
        # Canal hacia el FrontendAgent. No hay llamada directa entre agentes.
        ctx.datos["endpoints"] = rutas
        ctx.datos["router_generado"] = str(archivo)

        await self.log(ctx, f"{len(rutas)} endpoints generados: {', '.join(rutas)}")
        return [_relativa(archivo)]


def _limpiar_cercas(texto: str) -> str:
    """Quita las cercas de markdown que un LLM suele agregar pese a pedirle que no."""
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
