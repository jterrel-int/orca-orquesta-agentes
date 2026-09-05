"use client";

import { useEffect, useState } from "react";
import { desconectarVercel, estadoVercel, urlConectarVercel } from "@/lib/api";
import type { EstadoVercel } from "@/lib/types";

/**
 * El botón abre una ventana emergente hacia /api/vercel/oauth/iniciar, que
 * redirige a Vercel. El callback del backend cierra esa ventana solo cuando
 * termina; acá solo hace falta notar que se cerró y refrescar el estado.
 */
export default function ConexionVercel() {
  const [estado, setEstado] = useState<EstadoVercel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conectando, setConectando] = useState(false);

  async function refrescar() {
    try {
      setEstado(await estadoVercel());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo consultar el estado de Vercel");
    }
  }

  useEffect(() => {
    refrescar();
  }, []);

  function conectar() {
    setError(null);
    setConectando(true);
    const popup = window.open(urlConectarVercel(), "conectar-vercel", "width=480,height=640");

    if (!popup) {
      setConectando(false);
      setError("El navegador bloqueó la ventana emergente; habilitala e intentá de nuevo");
      return;
    }

    const intervalo = setInterval(() => {
      if (popup.closed) {
        clearInterval(intervalo);
        setConectando(false);
        refrescar();
      }
    }, 500);
  }

  async function desconectar() {
    try {
      await desconectarVercel();
      await refrescar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo desconectar");
    }
  }

  return (
    <div className="tarjeta-conexion">
      <div className="cabecera-conexion">
        <strong>Vercel</strong>
        <span className={`pastilla ${estado?.conectado ? "viva" : ""}`}>
          {estado?.conectado ? "Conectado" : "No conectado"}
        </span>
      </div>

      {estado?.conectado && estado.team_id && (
        <p className="apagado" style={{ margin: "0.35rem 0" }}>
          Team: <span className="mono">{estado.team_id}</span>
        </p>
      )}

      {error && <p className="error">{error}</p>}

      <div className="fila-alta" style={{ marginTop: "0.5rem" }}>
        {estado?.conectado ? (
          <button onClick={desconectar}>Desconectar</button>
        ) : (
          <button className="primario" onClick={conectar} disabled={conectando}>
            {conectando ? "Esperando autorización…" : "Conectar con Vercel"}
          </button>
        )}
      </div>
    </div>
  );
}
