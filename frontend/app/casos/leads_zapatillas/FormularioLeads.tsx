// Generado por FrontendAgent — no editar a mano.
"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

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
