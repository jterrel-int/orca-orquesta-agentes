// Generado por FrontendAgent — no editar a mano.
"use client";

import { useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

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
