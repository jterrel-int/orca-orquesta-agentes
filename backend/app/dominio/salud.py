"""Signos vitales de la fábrica: confianza por diseño.

En vez de frenar cada encargo con una aprobación humana, se vigila la salud
del sistema completo — volumen, tasa de rechazo, costo, cuellos de botella —
y se alerta cuando algo se sale de rango. Un monitor de UCI, no solo un
contador de errores 500.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from .fabrica import (
    ESTADOS_ACTIVOS,
    Encargo,
    MetricaEtapa,
    RegistroBitacora,
    primer_registro_roto,
)
from .puertos import BitacoraInmutable, RepositorioEncargos, RepositorioMetricas

Nivel = Literal["ok", "atencion", "critico"]
_GRAVEDAD: dict[Nivel, int] = {"ok": 0, "atencion": 1, "critico": 2}


@dataclass(frozen=True)
class Alerta:
    nivel: Nivel
    signo: str
    mensaje: str


@dataclass(frozen=True)
class SignosVitales:
    estado_general: Nivel
    encargos_total: int
    encargos_24h: int
    encargos_activos: int
    esperando_humano: int
    especificaciones_aprobadas: int
    especificaciones_fallidas: int
    tasa_aprobacion_primer_intento: float | None
    rechazos_por_causa: dict[str, int]
    costo_total_usd: float
    costo_promedio_encargo_usd: float | None
    duracion_media_por_etapa_s: dict[str, float]
    costo_por_etapa_usd: dict[str, float]
    bitacora_integra: bool
    alertas: list[Alerta] = field(default_factory=list)


@dataclass(frozen=True)
class PuntoVelocidad:
    dia: str
    encargos: int
    especificaciones_aprobadas: int
    costo_usd: float
    duracion_total_s: float


def _parsear(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def calcular_signos_vitales(
    encargos: list[Encargo],
    metricas: list[MetricaEtapa],
    *,
    bitacora_integra: bool,
    ahora: datetime,
    presupuesto_encargo_usd: float,
) -> SignosVitales:
    especs = [e for enc in encargos for e in enc.especificaciones]
    aprobadas = [e for e in especs if e.estado == "aprobada"]
    fallidas = [e for e in especs if e.estado in ("fallida", "bloqueada")]
    terminadas = aprobadas + fallidas
    tasa_primer_intento = (
        sum(1 for e in aprobadas if e.intentos <= 1) / len(terminadas) if terminadas else None
    )

    hace_24h = ahora - timedelta(hours=24)
    recientes = [
        enc for enc in encargos if (t := _parsear(enc.creado_en)) is not None and t >= hace_24h
    ]

    rechazos: dict[str, int] = defaultdict(int)
    duraciones: dict[str, list[float]] = defaultdict(list)
    costos: dict[str, float] = defaultdict(float)
    for m in metricas:
        duraciones[m.etapa].append(m.duracion_s)
        costos[m.etapa] += m.costo_usd or 0.0
        if m.etapa == "diagnostico":
            rechazos[m.resultado] += 1

    costo_total = sum(enc.costo_usd for enc in encargos)
    costo_promedio = costo_total / len(encargos) if encargos else None
    esperando = sum(1 for enc in encargos if enc.estado == "esperando_humano")

    alertas: list[Alerta] = []
    if not bitacora_integra:
        alertas.append(
            Alerta("critico", "bitacora", "La cadena de la bitácora está rota: alguien la alteró")
        )
    if terminadas:
        tasa_fallo = len(fallidas) / len(terminadas)
        if tasa_fallo > 0.3:
            alertas.append(
                Alerta("critico", "rechazos", f"{tasa_fallo:.0%} de especificaciones fallan")
            )
        elif tasa_fallo > 0.1:
            alertas.append(
                Alerta("atencion", "rechazos", f"{tasa_fallo:.0%} de especificaciones fallan")
            )
    if rechazos.get("harness", 0) > 0:
        alertas.append(
            Alerta(
                "atencion",
                "harness",
                f"{rechazos['harness']} fallo(s) atribuidos al entorno, no al código",
            )
        )
    if esperando:
        alertas.append(
            Alerta("atencion", "humano", f"{esperando} encargo(s) esperando una decisión humana")
        )
    if (
        presupuesto_encargo_usd > 0
        and costo_promedio is not None
        and costo_promedio > presupuesto_encargo_usd * 0.8
    ):
        alertas.append(
            Alerta(
                "atencion",
                "costo",
                f"Costo promedio USD {costo_promedio:.2f} cerca del tope "
                f"USD {presupuesto_encargo_usd:.2f}",
            )
        )
    if encargos and not recientes:
        alertas.append(Alerta("atencion", "volumen", "Ningún encargo nuevo en 24 horas"))

    estado: Nivel = "ok"
    for a in alertas:
        if _GRAVEDAD[a.nivel] > _GRAVEDAD[estado]:
            estado = a.nivel

    return SignosVitales(
        estado_general=estado,
        encargos_total=len(encargos),
        encargos_24h=len(recientes),
        encargos_activos=sum(1 for enc in encargos if enc.estado in ESTADOS_ACTIVOS),
        esperando_humano=esperando,
        especificaciones_aprobadas=len(aprobadas),
        especificaciones_fallidas=len(fallidas),
        tasa_aprobacion_primer_intento=tasa_primer_intento,
        rechazos_por_causa=dict(rechazos),
        costo_total_usd=round(costo_total, 6),
        costo_promedio_encargo_usd=round(costo_promedio, 6) if costo_promedio is not None else None,
        duracion_media_por_etapa_s={
            etapa: round(sum(v) / len(v), 2) for etapa, v in duraciones.items()
        },
        costo_por_etapa_usd={etapa: round(c, 6) for etapa, c in costos.items()},
        bitacora_integra=bitacora_integra,
        alertas=alertas,
    )


def velocidad_historica(
    encargos: list[Encargo], metricas: list[MetricaEtapa], *, ahora: datetime, dias: int = 14
) -> list[PuntoVelocidad]:
    """Una fila por día (UTC), del más viejo al más reciente, incluidos los
    días sin actividad — un hueco también es un dato.
    """
    inicio = (ahora - timedelta(days=dias - 1)).date()
    claves = [(inicio + timedelta(days=i)).isoformat() for i in range(dias)]
    n_encargos: dict[str, int] = defaultdict(int)
    aprobadas: dict[str, int] = defaultdict(int)
    costo: dict[str, float] = defaultdict(float)
    duracion: dict[str, float] = defaultdict(float)

    for enc in encargos:
        if (t := _parsear(enc.creado_en)) is not None:
            n_encargos[t.date().isoformat()] += 1
    for m in metricas:
        t = _parsear(m.ts)
        if t is None:
            continue
        dia = t.date().isoformat()
        costo[dia] += m.costo_usd or 0.0
        duracion[dia] += m.duracion_s
        if m.etapa == "verificacion" and m.resultado == "ok":
            aprobadas[dia] += 1

    return [
        PuntoVelocidad(
            dia=d,
            encargos=n_encargos[d],
            especificaciones_aprobadas=aprobadas[d],
            costo_usd=round(costo[d], 6),
            duracion_total_s=round(duracion[d], 2),
        )
        for d in claves
    ]


@dataclass(frozen=True)
class Integridad:
    integra: bool
    registros: int
    primer_registro_roto: int | None


class ServicioSaludFabrica:
    def __init__(
        self,
        encargos: RepositorioEncargos,
        metricas: RepositorioMetricas,
        bitacora: BitacoraInmutable,
        presupuesto_encargo_usd: float,
    ) -> None:
        self._encargos = encargos
        self._metricas = metricas
        self._bitacora = bitacora
        self._presupuesto = presupuesto_encargo_usd

    async def encargos(self) -> list[Encargo]:
        return await self._encargos.listar()

    async def bitacora(self, encargo_id: str) -> list[RegistroBitacora]:
        return await self._bitacora.listar(encargo_id)

    async def metricas(self, encargo_id: str) -> list[MetricaEtapa]:
        return await self._metricas.listar(encargo_id)

    async def integridad(self) -> Integridad:
        registros = await self._bitacora.listar()
        roto = primer_registro_roto(registros)
        return Integridad(roto is None, len(registros), roto)

    async def signos_vitales(self, ahora: datetime) -> SignosVitales:
        return calcular_signos_vitales(
            await self._encargos.listar(),
            await self._metricas.listar(),
            bitacora_integra=(await self.integridad()).integra,
            ahora=ahora,
            presupuesto_encargo_usd=self._presupuesto,
        )

    async def velocidad(self, ahora: datetime, dias: int = 14) -> list[PuntoVelocidad]:
        return velocidad_historica(
            await self._encargos.listar(), await self._metricas.listar(), ahora=ahora, dias=dias
        )
