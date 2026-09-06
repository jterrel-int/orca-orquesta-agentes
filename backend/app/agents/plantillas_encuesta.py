"""Plantillas del caso de uso "encuesta": router de backend y componente de
frontend.
"""

ROUTER_ENCUESTA = '''"""Generado por BackendAgent — no editar a mano.

Caso de uso "Encuesta de satisfacción": router de FastAPI autocontenido en
/api/encuesta. Respuestas de 1 a 5 con comentario opcional, más un endpoint
de resultados agregados.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..adaptadores.persistencia_sqlalchemy import Base, FabricaSesion

router = APIRouter(prefix="/api/encuesta", tags=["encuesta (generado)"])


def _ahora() -> datetime:
    return datetime.now(UTC)


class EncuestaRespuestaORM(Base):
    __tablename__ = "encuesta_respuestas"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    puntaje: Mapped[int] = mapped_column(Integer, nullable=False)
    comentario: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class RespuestaEntrada(BaseModel):
    puntaje: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=500)


class RespuestaSalida(BaseModel):
    id: int
    puntaje: int
    comentario: str | None
    creado_en: datetime


class ResultadosSalida(BaseModel):
    total: int
    promedio: float
    conteo_por_puntaje: dict[int, int]


async def _sesion() -> AsyncIterator[AsyncSession]:
    async with FabricaSesion() as sesion:
        yield sesion


@router.post("", response_model=RespuestaSalida, status_code=status.HTTP_201_CREATED)
async def crear_respuesta(
    datos: RespuestaEntrada, sesion: AsyncSession = Depends(_sesion)
) -> RespuestaSalida:
    fila = EncuestaRespuestaORM(puntaje=datos.puntaje, comentario=datos.comentario)
    sesion.add(fila)
    await sesion.commit()
    await sesion.refresh(fila)
    return RespuestaSalida(
        id=fila.id, puntaje=fila.puntaje, comentario=fila.comentario, creado_en=fila.creado_en
    )


@router.get("/resultados", response_model=ResultadosSalida)
async def resultados(sesion: AsyncSession = Depends(_sesion)) -> ResultadosSalida:
    filas = (await sesion.execute(select(EncuestaRespuestaORM))).scalars().all()
    conteo = dict.fromkeys(range(1, 6), 0)
    for f in filas:
        conteo[f.puntaje] = conteo.get(f.puntaje, 0) + 1
    total = len(filas)
    promedio = (sum(f.puntaje for f in filas) / total) if total else 0.0
    return ResultadosSalida(total=total, promedio=round(promedio, 2), conteo_por_puntaje=conteo)
'''


ENCUESTA_TSX = """// Generado por FrontendAgent — no editar a mano.
"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\\/$/, "") ?? "http://localhost:8000";

type Resultados = {
  total: number;
  promedio: number;
  conteo_por_puntaje: Record<string, number>;
};

export default function Encuesta() {
  const [puntaje, setPuntaje] = useState(5);
  const [comentario, setComentario] = useState("");
  const [resultados, setResultados] = useState<Resultados | null>(null);
  const [enviado, setEnviado] = useState(false);

  async function refrescar() {
    const res = await fetch(`${API}/api/encuesta/resultados`, { cache: "no-store" });
    if (res.ok) setResultados(await res.json());
  }

  useEffect(() => {
    refrescar();
  }, []);

  async function enviar() {
    await fetch(`${API}/api/encuesta`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ puntaje, comentario: comentario || null }),
    });
    setComentario("");
    setEnviado(true);
    refrescar();
  }

  return (
    <div className="encuesta">
      <div className="fila-alta">
        <select
          value={puntaje}
          onChange={(e) => setPuntaje(Number(e.target.value))}
          aria-label="Puntaje"
        >
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <input
          value={comentario}
          onChange={(e) => setComentario(e.target.value)}
          placeholder="Comentario (opcional)"
          aria-label="Comentario"
        />
        <button onClick={enviar}>Enviar</button>
      </div>

      {enviado && <p className="apagado">¡Gracias por tu respuesta!</p>}

      {resultados && (
        <div className="resultados-encuesta">
          <p>
            {resultados.total} respuestas · promedio {resultados.promedio}
          </p>
          {[1, 2, 3, 4, 5].map((n) => {
            const cantidad = resultados.conteo_por_puntaje[String(n)] ?? 0;
            const ancho = resultados.total ? (cantidad / resultados.total) * 100 : 0;
            return (
              <div key={n} className="barra-encuesta">
                <span>{n}</span>
                <div className="barra-fondo">
                  <div className="barra-relleno" style={{ width: `${ancho}%` }} />
                </div>
                <span>{cantidad}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
"""
