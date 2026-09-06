"""Plantillas del caso de uso "calculadora": router de backend y componente
de frontend. Viven separadas de plantillas.py porque son bastante más largas
que las de Item, no porque cambie el patrón.
"""

ROUTER_CALCULADORA = '''"""Generado por BackendAgent — no editar a mano.

Caso de uso "Calculadora con login e historial": router de FastAPI
autocontenido en /api/calculadora. Reutiliza el motor/FabricaSesion de
persistencia_sqlalchemy (mismo SQLite que el resto de la app) con tablas
propias: usuarios, sesiones y operaciones.
"""

import hashlib
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..adaptadores.persistencia_sqlalchemy import Base, FabricaSesion

router = APIRouter(prefix="/api/calculadora", tags=["calculadora (generado)"])


def _ahora() -> datetime:
    return datetime.now(UTC)


class CalculadoraUsuarioORM(Base):
    __tablename__ = "calculadora_usuarios"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # unique=True alcanza para el lookup por usuario; sin index=True a propósito:
    # el router puede montarse más de una vez en el mismo proceso (cada corrida
    # nueva lo vuelve a importar) y un Index con nombre fijo no sobrevive a esa
    # redefinición sobre la misma Base compartida, aunque extend_existing sí.
    usuario: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    clave_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class CalculadoraSesionORM(Base):
    __tablename__ = "calculadora_sesiones"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("calculadora_usuarios.id"), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class CalculadoraOperacionORM(Base):
    __tablename__ = "calculadora_operaciones"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("calculadora_usuarios.id"), nullable=False)
    a: Mapped[float] = mapped_column(Float, nullable=False)
    b: Mapped[float] = mapped_column(Float, nullable=False)
    operador: Mapped[str] = mapped_column(String(1), nullable=False)
    resultado: Mapped[float] = mapped_column(Float, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class RegistroEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=80)
    clave: str = Field(min_length=1, max_length=200)


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=80)
    clave: str = Field(min_length=1, max_length=200)


class OperarEntrada(BaseModel):
    a: float
    b: float
    operador: str = Field(pattern="^[+*/-]$")


class OperacionSalida(BaseModel):
    id: int
    a: float
    b: float
    operador: str
    resultado: float
    creado_en: datetime


def _hashear_clave(clave: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", clave.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


async def _sesion() -> AsyncIterator[AsyncSession]:
    async with FabricaSesion() as sesion:
        yield sesion


async def _usuario_autenticado(
    authorization: str | None = Header(default=None),
    sesion: AsyncSession = Depends(_sesion),
) -> CalculadoraUsuarioORM:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el token de sesión")
    token = authorization.removeprefix("Bearer ").strip()
    fila_sesion = (
        await sesion.execute(
            select(CalculadoraSesionORM).where(CalculadoraSesionORM.token == token)
        )
    ).scalar_one_or_none()
    if fila_sesion is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    usuario = await sesion.get(CalculadoraUsuarioORM, fila_sesion.usuario_id)
    if usuario is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return usuario


@router.post("/registro", status_code=status.HTTP_201_CREATED)
async def registro(
    datos: RegistroEntrada, sesion: AsyncSession = Depends(_sesion)
) -> dict[str, str]:
    existente = (
        await sesion.execute(
            select(CalculadoraUsuarioORM).where(CalculadoraUsuarioORM.usuario == datos.usuario)
        )
    ).scalar_one_or_none()
    if existente is not None:
        raise HTTPException(status_code=409, detail="El usuario ya existe")

    salt = secrets.token_hex(16)
    fila = CalculadoraUsuarioORM(
        usuario=datos.usuario, salt=salt, clave_hash=_hashear_clave(datos.clave, salt)
    )
    sesion.add(fila)
    await sesion.commit()
    return {"usuario": datos.usuario}


@router.post("/login")
async def login(datos: LoginEntrada, sesion: AsyncSession = Depends(_sesion)) -> dict[str, str]:
    fila = (
        await sesion.execute(
            select(CalculadoraUsuarioORM).where(CalculadoraUsuarioORM.usuario == datos.usuario)
        )
    ).scalar_one_or_none()
    if fila is None or _hashear_clave(datos.clave, fila.salt) != fila.clave_hash:
        raise HTTPException(status_code=401, detail="Usuario o clave incorrectos")

    token = secrets.token_hex(32)
    sesion.add(CalculadoraSesionORM(token=token, usuario_id=fila.id))
    await sesion.commit()
    return {"token": token}


@router.post("/operar", response_model=OperacionSalida)
async def operar(
    datos: OperarEntrada,
    usuario: CalculadoraUsuarioORM = Depends(_usuario_autenticado),
    sesion: AsyncSession = Depends(_sesion),
) -> OperacionSalida:
    if datos.operador == "+":
        resultado = datos.a + datos.b
    elif datos.operador == "-":
        resultado = datos.a - datos.b
    elif datos.operador == "*":
        resultado = datos.a * datos.b
    else:
        if datos.b == 0:
            raise HTTPException(status_code=400, detail="No se puede dividir por cero")
        resultado = datos.a / datos.b

    fila = CalculadoraOperacionORM(
        usuario_id=usuario.id,
        a=datos.a,
        b=datos.b,
        operador=datos.operador,
        resultado=resultado,
    )
    sesion.add(fila)
    await sesion.commit()
    await sesion.refresh(fila)
    return OperacionSalida(
        id=fila.id,
        a=fila.a,
        b=fila.b,
        operador=fila.operador,
        resultado=fila.resultado,
        creado_en=fila.creado_en,
    )


@router.get("/historial", response_model=list[OperacionSalida])
async def historial(
    usuario: CalculadoraUsuarioORM = Depends(_usuario_autenticado),
    sesion: AsyncSession = Depends(_sesion),
) -> list[OperacionSalida]:
    filas = (
        (
            await sesion.execute(
                select(CalculadoraOperacionORM)
                .where(CalculadoraOperacionORM.usuario_id == usuario.id)
                .order_by(CalculadoraOperacionORM.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        OperacionSalida(
            id=f.id,
            a=f.a,
            b=f.b,
            operador=f.operador,
            resultado=f.resultado,
            creado_en=f.creado_en,
        )
        for f in filas
    ]
'''


CALCULADORA_TSX = """// Generado por FrontendAgent — no editar a mano.
"use client";

import { useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\\/$/, "") ?? "http://localhost:8000";

type Operacion = {
  id: number;
  a: number;
  b: number;
  operador: string;
  resultado: number;
  creado_en: string;
};

export default function Calculadora() {
  const [token, setToken] = useState<string | null>(null);
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [modoRegistro, setModoRegistro] = useState(false);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [operador, setOperador] = useState("+");
  const [historial, setHistorial] = useState<Operacion[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refrescarHistorial(tok: string) {
    const res = await fetch(`${API}/api/calculadora/historial`, {
      headers: { Authorization: `Bearer ${tok}` },
    });
    if (res.ok) setHistorial(await res.json());
  }

  async function autenticar() {
    setError(null);
    try {
      const ruta = modoRegistro ? "/api/calculadora/registro" : "/api/calculadora/login";
      const res = await fetch(`${API}${ruta}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usuario, clave }),
      });
      if (!res.ok) {
        const detalle = await res.json().catch(() => null);
        throw new Error(detalle?.detail ?? "Error de autenticación");
      }
      if (modoRegistro) {
        setModoRegistro(false);
        return;
      }
      const datos = await res.json();
      setToken(datos.token);
      await refrescarHistorial(datos.token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    }
  }

  async function operar() {
    if (!token) return;
    setError(null);
    try {
      const res = await fetch(`${API}/api/calculadora/operar`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ a: Number(a), b: Number(b), operador }),
      });
      if (!res.ok) {
        const detalle = await res.json().catch(() => null);
        throw new Error(detalle?.detail ?? "Error al operar");
      }
      await refrescarHistorial(token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    }
  }

  function cerrarSesion() {
    setToken(null);
    setHistorial([]);
  }

  if (!token) {
    return (
      <div className="calculadora-login">
        <h2>{modoRegistro ? "Crear cuenta" : "Iniciar sesión"}</h2>
        <input
          value={usuario}
          onChange={(e) => setUsuario(e.target.value)}
          placeholder="Usuario"
          aria-label="Usuario"
        />
        <input
          value={clave}
          onChange={(e) => setClave(e.target.value)}
          type="password"
          placeholder="Clave"
          aria-label="Clave"
        />
        {error && <p className="error">{error}</p>}
        <button onClick={autenticar}>{modoRegistro ? "Registrarme" : "Entrar"}</button>
        <button className="icono" onClick={() => setModoRegistro((v) => !v)}>
          {modoRegistro ? "Ya tengo cuenta" : "Crear una cuenta"}
        </button>
      </div>
    );
  }

  return (
    <div className="calculadora">
      <div className="fila-alta">
        <input value={a} onChange={(e) => setA(e.target.value)} placeholder="a" aria-label="a" />
        <select
          value={operador}
          onChange={(e) => setOperador(e.target.value)}
          aria-label="operador"
        >
          <option value="+">+</option>
          <option value="-">-</option>
          <option value="*">×</option>
          <option value="/">÷</option>
        </select>
        <input value={b} onChange={(e) => setB(e.target.value)} placeholder="b" aria-label="b" />
        <button onClick={operar}>Calcular</button>
        <button className="icono" onClick={cerrarSesion}>
          Cerrar sesión
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {historial.length === 0 ? (
        <p className="apagado">Todavía no hiciste ninguna operación.</p>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Operación</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            {historial.map((op) => (
              <tr key={op.id}>
                <td className="mono">
                  {op.a} {op.operador} {op.b}
                </td>
                <td className="mono">{op.resultado}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
"""
