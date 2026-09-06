// Generado por FrontendAgent — no editar a mano.
"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

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
