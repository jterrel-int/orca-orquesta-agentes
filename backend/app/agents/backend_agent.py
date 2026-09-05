"""Agente 1: genera el modelo y los endpoints CRUD del backend."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..adaptadores.fabricas import construir_cerebro
from ..config import config
from ..dominio.puertos import Cerebro
from .base import Agente, ContextoCorrida
from .plantillas import ROUTER_ITEMS

INSTRUCCION = (
    "Escribe un router de FastAPI con CRUD completo para la entidad Item "
    "(id, name). Usa SQLAlchemy async, dependencia obtener_sesion y los "
    "esquemas ItemCrear/ItemActualizar/ItemLeer ya existentes. "
    "Devuelve solo código Python, sin explicación ni cercas de markdown."
)


class BackendAgent(Agente):
    name = "backend"

    def __init__(self, cerebro: Cerebro | None = None) -> None:
        self._cerebro = cerebro or construir_cerebro()

    async def ejecutar(self, ctx: ContextoCorrida) -> list[str]:
        destino = Path(config.dir_generado_backend)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "__init__.py").touch(exist_ok=True)

        await self.log(ctx, "Definiendo el modelo Item (id, name, creado_en)")
        await asyncio.sleep(0.4)

        await self.log(ctx, "Generando el router CRUD de FastAPI")
        codigo = await self._cerebro.pensar(
            INSTRUCCION,
            contexto="Modelo: Item(id: int, name: str). Prefijo: /api/items",
            respaldo=ROUTER_ITEMS,
        )
        codigo = _limpiar_cercas(codigo)

        # Un LLM puede devolver algo que no compila. Verificar antes de escribir
        # es la diferencia entre un agente y un generador de texto.
        await self.log(ctx, "Verificando que el código generado compile")
        try:
            compile(codigo, "<generado>", "exec")
        except SyntaxError as e:
            await self.log(ctx, f"El código generado no compila ({e}); se usa la plantilla")
            codigo = ROUTER_ITEMS

        archivo = destino / "item_routes.py"
        archivo.write_text(codigo, encoding="utf-8")
        await asyncio.sleep(0.3)

        rutas = ["GET /api/items", "POST /api/items", "GET /api/items/{id}",
                 "PUT /api/items/{id}", "DELETE /api/items/{id}"]
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
