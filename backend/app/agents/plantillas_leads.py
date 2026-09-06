"""Plantillas del caso de uso "leads_zapatillas": router de backend y
componente de frontend.
"""

ROUTER_LEADS = '''"""Generado por BackendAgent — no editar a mano.

Caso de uso "Leads de zapatillas": router de FastAPI autocontenido en
/api/leads. Es una demo pública a propósito: sin autenticación, cualquiera
puede dejar sus datos igual que en un formulario de captación real.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..adaptadores.persistencia_sqlalchemy import Base, FabricaSesion

router = APIRouter(prefix="/api/leads", tags=["leads (generado)"])


def _ahora() -> datetime:
    return datetime.now(UTC)


class LeadORM(Base):
    __tablename__ = "leads_zapatillas"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    telefono: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    talla: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    comentario: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class LeadEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    telefono: str = Field(default="", max_length=40)
    talla: str = Field(default="", max_length=20)
    comentario: str = Field(default="", max_length=500)

    @field_validator("email")
    @classmethod
    def _validar_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("email inválido: falta '@'")
        return v


class LeadSalida(BaseModel):
    id: int
    nombre: str
    email: str
    telefono: str
    talla: str
    comentario: str
    creado_en: datetime


def _a_salida(fila: LeadORM) -> LeadSalida:
    return LeadSalida(
        id=fila.id,
        nombre=fila.nombre,
        email=fila.email,
        telefono=fila.telefono,
        talla=fila.talla,
        comentario=fila.comentario,
        creado_en=fila.creado_en,
    )


async def _sesion() -> AsyncIterator[AsyncSession]:
    async with FabricaSesion() as sesion:
        yield sesion


@router.post("", response_model=LeadSalida, status_code=status.HTTP_201_CREATED)
async def crear_lead(datos: LeadEntrada, sesion: AsyncSession = Depends(_sesion)) -> LeadSalida:
    fila = LeadORM(
        nombre=datos.nombre,
        email=datos.email,
        telefono=datos.telefono,
        talla=datos.talla,
        comentario=datos.comentario,
    )
    sesion.add(fila)
    await sesion.commit()
    await sesion.refresh(fila)
    return _a_salida(fila)


@router.get("", response_model=list[LeadSalida])
async def listar_leads(sesion: AsyncSession = Depends(_sesion)) -> list[LeadSalida]:
    filas = (await sesion.execute(select(LeadORM).order_by(LeadORM.id.desc()))).scalars().all()
    return [_a_salida(f) for f in filas]
'''


FORMULARIO_LEADS_TSX = """// Generado por FrontendAgent — no editar a mano.
"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\\/$/, "") ?? "http://localhost:8000";

type Lead = {
  id: number;
  nombre: string;
  email: string;
  telefono: string;
  talla: string;
  comentario: string;
  creado_en: string;
};

export default function FormularioLeads() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [telefono, setTelefono] = useState("");
  const [talla, setTalla] = useState("");
  const [comentario, setComentario] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refrescar() {
    const res = await fetch(`${API}/api/leads`, { cache: "no-store" });
    if (res.ok) setLeads(await res.json());
  }

  useEffect(() => {
    refrescar();
  }, []);

  async function enviar() {
    setError(null);
    setEnviado(false);
    try {
      const res = await fetch(`${API}/api/leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre, email, telefono, talla, comentario }),
      });
      if (!res.ok) throw new Error("Revisá el nombre y el email");
      setNombre("");
      setEmail("");
      setTelefono("");
      setTalla("");
      setComentario("");
      setEnviado(true);
      refrescar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    }
  }

  return (
    <div className="formulario-leads">
      <div className="fila-alta">
        <input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Nombre"
          aria-label="Nombre"
        />
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          aria-label="Email"
        />
        <input
          value={telefono}
          onChange={(e) => setTelefono(e.target.value)}
          placeholder="Teléfono"
          aria-label="Teléfono"
        />
        <input
          value={talla}
          onChange={(e) => setTalla(e.target.value)}
          placeholder="Talla"
          aria-label="Talla"
        />
        <input
          value={comentario}
          onChange={(e) => setComentario(e.target.value)}
          placeholder="Comentario"
          aria-label="Comentario"
        />
        <button onClick={enviar} disabled={!nombre.trim() || !email.includes("@")}>
          Enviar
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {enviado && <p className="apagado">¡Gracias! Te vamos a contactar pronto.</p>}

      {leads.length === 0 ? (
        <p className="apagado">Todavía no hay leads capturados.</p>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Email</th>
              <th>Talla</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((l) => (
              <tr key={l.id}>
                <td>{l.nombre}</td>
                <td>{l.email}</td>
                <td>{l.talla}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
"""
