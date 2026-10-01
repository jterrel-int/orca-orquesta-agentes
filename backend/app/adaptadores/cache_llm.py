"""Caché de respuestas del LLM para la fábrica. Opt-in (FABRICA_CACHE_LLM).

Envuelve a un cerebro medido: la misma (modelo, instrucción, contexto) ya
pagada una vez no se vuelve a pagar. Sirve sobre todo en reintentos y al
reanudar un encargo, que reconstruyen prompts idénticos.

Por qué está apagada por defecto: un LLM no es determinista, y la caché fija
la primera muestra en vez de sacar una nueva. Para la fábrica eso es una
ventaja (reproducibilidad), pero es una decisión, no algo a hacer en silencio.

Reglas:
- Un acierto devuelve consumo 0 y modelo "cache:<modelo>": no cuenta como
  gasto. El ahorro se lleva aparte, en la propia fila de la caché.
- Nunca se guarda un respaldo: si el cerebro falló y devolvió el texto de
  respaldo (0 tokens de salida), no hay nada que valga la pena fijar.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from ..dominio.fabrica import Consumo, RespuestaMedida
from ..dominio.puertos import CerebroMedido
from .persistencia_sqlalchemy import Base, _ahora


class EntradaCacheORM(Base):
    __tablename__ = "fabrica_cache_llm"

    clave: Mapped[str] = mapped_column(String(64), primary_key=True)
    modelo: Mapped[str] = mapped_column(String(80), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_entrada: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    aciertos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


def clave_cache(modelo: str, instruccion: str, contexto: str) -> str:
    canonico = json.dumps(
        [modelo, instruccion, contexto], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


class CerebroConCache:
    nombre = "cache"

    def __init__(
        self, interno: CerebroMedido, modelo: str, sesiones: async_sessionmaker[AsyncSession]
    ) -> None:
        self._interno = interno
        self._modelo = modelo
        self._sesiones = sesiones

    async def pensar(self, instruccion: str, contexto: str = "", *, respaldo: str = "") -> str:
        return (await self.pensar_medido(instruccion, contexto, respaldo=respaldo)).texto

    async def pensar_medido(
        self, instruccion: str, contexto: str = "", *, respaldo: str = ""
    ) -> RespuestaMedida:
        clave = clave_cache(self._modelo, instruccion, contexto)
        async with self._sesiones() as sesion:
            fila = await sesion.get(EntradaCacheORM, clave)
            if fila is not None:
                fila.aciertos += 1
                await sesion.commit()
                return RespuestaMedida(fila.texto, Consumo(f"cache:{fila.modelo}", 0, 0, 0.0))

        r = await self._interno.pensar_medido(instruccion, contexto, respaldo=respaldo)
        if r.consumo.tokens_salida > 0 and r.texto != respaldo:
            async with self._sesiones() as sesion:
                await sesion.merge(
                    EntradaCacheORM(
                        clave=clave,
                        modelo=r.consumo.modelo,
                        texto=r.texto,
                        tokens_entrada=r.consumo.tokens_entrada,
                        tokens_salida=r.consumo.tokens_salida,
                        costo_usd=r.consumo.costo_usd,
                    )
                )
                await sesion.commit()
        return r


async def estado_cache(sesiones: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    """Entradas, aciertos y ahorro estimado (informativo: nunca se resta del
    gasto real).
    """
    async with sesiones() as sesion:
        entradas, aciertos, ahorro, tokens = (
            await sesion.execute(
                select(
                    func.count(EntradaCacheORM.clave),
                    func.coalesce(func.sum(EntradaCacheORM.aciertos), 0),
                    func.coalesce(
                        func.sum(EntradaCacheORM.aciertos * EntradaCacheORM.costo_usd), 0.0
                    ),
                    func.coalesce(
                        func.sum(
                            EntradaCacheORM.aciertos
                            * (EntradaCacheORM.tokens_entrada + EntradaCacheORM.tokens_salida)
                        ),
                        0,
                    ),
                )
            )
        ).one()
    return {
        "entradas": int(entradas),
        "aciertos": int(aciertos),
        "ahorro_estimado_usd": round(float(ahorro), 6),
        "tokens_ahorrados": int(tokens),
    }


async def limpiar_cache(sesiones: async_sessionmaker[AsyncSession]) -> int:
    async with sesiones() as sesion:
        resultado = await sesion.execute(delete(EntradaCacheORM))
        await sesion.commit()
        return int(resultado.rowcount or 0)
