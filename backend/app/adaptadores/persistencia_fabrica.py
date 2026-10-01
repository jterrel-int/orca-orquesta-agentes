"""Persistencia de la fábrica: encargos, bitácora sellada y métricas por etapa.

A diferencia de los repositorios de persistencia_sqlalchemy.py (una sesión por
request HTTP), el Líder vive lo que dura un encargo — minutos, a veces con una
pausa humana en el medio —, así que cada operación abre y cierra su propia
sesión a partir de la fábrica de sesiones que recibe.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from ..dominio.fabrica import (
    HASH_GENESIS,
    Encargo,
    MetricaEtapa,
    RegistroBitacora,
    encargo_desde_dict,
    sellar,
)
from .persistencia_sqlalchemy import Base, _ahora

FabricaDeSesiones = async_sessionmaker[AsyncSession]


class EncargoORM(Base):
    """El encargo completo (especificaciones y preguntas incluidas) viaja como
    JSON: se lee y se escribe entero, nunca se consulta por dentro.
    """

    __tablename__ = "fabrica_encargos"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    datos: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class RegistroBitacoraORM(Base):
    __tablename__ = "fabrica_bitacora"

    secuencia: Mapped[int] = mapped_column(Integer, primary_key=True)
    encargo_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    agente: Mapped[str] = mapped_column(String(40), nullable=False)
    accion: Mapped[str] = mapped_column(String(80), nullable=False)
    evidencia: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[str] = mapped_column(String(40), nullable=False)
    hash_previo: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    def a_dominio(self) -> RegistroBitacora:
        return RegistroBitacora(
            secuencia=self.secuencia,
            encargo_id=self.encargo_id,
            agente=self.agente,
            accion=self.accion,
            evidencia=json.loads(self.evidencia),
            ts=self.ts,
            hash_previo=self.hash_previo,
            hash=self.hash,
        )


class MetricaEtapaORM(Base):
    __tablename__ = "fabrica_metricas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encargo_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    espec_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    etapa: Mapped[str] = mapped_column(String(30), nullable=False)
    agente: Mapped[str] = mapped_column(String(40), nullable=False)
    intento: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    modelo: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    tokens_entrada: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    duracion_s: Mapped[float] = mapped_column(Float, nullable=False)
    resultado: Mapped[str] = mapped_column(String(40), nullable=False)
    ts: Mapped[str] = mapped_column(String(40), nullable=False)

    def a_dominio(self) -> MetricaEtapa:
        return MetricaEtapa(
            encargo_id=self.encargo_id,
            etapa=self.etapa,  # type: ignore[arg-type]
            agente=self.agente,
            resultado=self.resultado,
            duracion_s=self.duracion_s,
            espec_id=self.espec_id,
            intento=self.intento,
            modelo=self.modelo,
            tokens_entrada=self.tokens_entrada,
            tokens_salida=self.tokens_salida,
            costo_usd=self.costo_usd,
            ts=self.ts,
        )


# SQLite no tiene permisos por tabla; un trigger que aborta es lo más
# parecido a un "append-only" que ofrece. No es criptografía — eso lo hace la
# cadena de hashes —, es la primera barrera contra un UPDATE descuidado.
_TRIGGERS_BITACORA = (
    """
    CREATE TRIGGER IF NOT EXISTS fabrica_bitacora_sin_update
    BEFORE UPDATE ON fabrica_bitacora
    BEGIN SELECT RAISE(ABORT, 'la bitácora es inmutable'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS fabrica_bitacora_sin_delete
    BEFORE DELETE ON fabrica_bitacora
    BEGIN SELECT RAISE(ABORT, 'la bitácora es inmutable'); END
    """,
)


async def proteger_bitacora(conexion: AsyncConnection) -> None:
    if conexion.dialect.name != "sqlite":
        return
    for sentencia in _TRIGGERS_BITACORA:
        await conexion.execute(text(sentencia))


class RepositorioEncargosSQLAlchemy:
    def __init__(self, sesiones: FabricaDeSesiones) -> None:
        self._sesiones = sesiones

    async def guardar(self, encargo: Encargo) -> None:
        async with self._sesiones() as sesion:
            fila = await sesion.get(EncargoORM, encargo.id)
            datos = json.dumps(encargo.a_dict(), ensure_ascii=False)
            if fila is None:
                sesion.add(EncargoORM(id=encargo.id, estado=encargo.estado, datos=datos))
            else:
                fila.estado = encargo.estado
                fila.datos = datos
            await sesion.commit()

    async def obtener(self, encargo_id: str) -> Encargo | None:
        async with self._sesiones() as sesion:
            fila = await sesion.get(EncargoORM, encargo_id)
            return encargo_desde_dict(json.loads(fila.datos)) if fila else None

    async def listar(self) -> list[Encargo]:
        async with self._sesiones() as sesion:
            filas = await sesion.scalars(select(EncargoORM).order_by(EncargoORM.creado_en.desc()))
            return [encargo_desde_dict(json.loads(f.datos)) for f in filas]


class BitacoraSQLAlchemy:
    """Una sola cadena global. El lock serializa los `registrar` de este
    proceso; la restricción UNIQUE sobre `hash` y la clave primaria sobre
    `secuencia` evitan que dos escritores bifurquen la cadena igual.
    """

    def __init__(self, sesiones: FabricaDeSesiones) -> None:
        self._sesiones = sesiones
        self._lock = asyncio.Lock()

    async def registrar(
        self, encargo_id: str, agente: str, accion: str, evidencia: dict[str, Any]
    ) -> RegistroBitacora:
        async with self._lock, self._sesiones() as sesion:
            ultimo = await sesion.scalar(
                select(RegistroBitacoraORM).order_by(RegistroBitacoraORM.secuencia.desc()).limit(1)
            )
            secuencia = (ultimo.secuencia + 1) if ultimo else 1
            previo = ultimo.hash if ultimo else HASH_GENESIS
            # Ida y vuelta por JSON antes de sellar: lo que se sella es
            # exactamente lo que se va a leer después.
            evidencia_json = json.loads(json.dumps(evidencia, ensure_ascii=False, default=str))
            registro = sellar(secuencia, encargo_id, agente, accion, evidencia_json, previo)
            sesion.add(
                RegistroBitacoraORM(
                    secuencia=registro.secuencia,
                    encargo_id=registro.encargo_id,
                    agente=registro.agente,
                    accion=registro.accion,
                    evidencia=json.dumps(registro.evidencia, ensure_ascii=False),
                    ts=registro.ts,
                    hash_previo=registro.hash_previo,
                    hash=registro.hash,
                )
            )
            await sesion.commit()
            return registro

    async def listar(self, encargo_id: str | None = None) -> list[RegistroBitacora]:
        async with self._sesiones() as sesion:
            consulta = select(RegistroBitacoraORM).order_by(RegistroBitacoraORM.secuencia)
            if encargo_id is not None:
                consulta = consulta.where(RegistroBitacoraORM.encargo_id == encargo_id)
            return [f.a_dominio() for f in await sesion.scalars(consulta)]


class RepositorioMetricasSQLAlchemy:
    def __init__(self, sesiones: FabricaDeSesiones) -> None:
        self._sesiones = sesiones

    async def registrar(self, metrica: MetricaEtapa) -> None:
        async with self._sesiones() as sesion:
            sesion.add(
                MetricaEtapaORM(
                    encargo_id=metrica.encargo_id,
                    espec_id=metrica.espec_id,
                    etapa=metrica.etapa,
                    agente=metrica.agente,
                    intento=metrica.intento,
                    modelo=metrica.modelo,
                    tokens_entrada=metrica.tokens_entrada,
                    tokens_salida=metrica.tokens_salida,
                    costo_usd=metrica.costo_usd,
                    duracion_s=metrica.duracion_s,
                    resultado=metrica.resultado,
                    ts=metrica.ts,
                )
            )
            await sesion.commit()

    async def listar(self, encargo_id: str | None = None) -> list[MetricaEtapa]:
        async with self._sesiones() as sesion:
            consulta = select(MetricaEtapaORM).order_by(MetricaEtapaORM.id)
            if encargo_id is not None:
                consulta = consulta.where(MetricaEtapaORM.encargo_id == encargo_id)
            return [f.a_dominio() for f in await sesion.scalars(consulta)]


async def tablas_existentes(sesiones: FabricaDeSesiones) -> list[str]:
    """Las tablas que ya viven en la base — el Especificador las usa para
    detectar un pedido que choca con una tabla legada.
    """
    async with sesiones() as sesion:
        conexion = await sesion.connection()
        if conexion.dialect.name != "sqlite":
            return []
        filas = await conexion.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        )
        return sorted(str(f[0]) for f in filas if not str(f[0]).startswith("fabrica_"))
