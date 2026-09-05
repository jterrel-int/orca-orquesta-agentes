"use client";

import { useEffect, useState } from "react";
import { conectarRender, desconectarRender, estadoRender } from "@/lib/api";
import type { EstadoRender } from "@/lib/types";

export default function ConexionRender() {
  const [estado, setEstado] = useState<EstadoRender | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [conectando, setConectando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refrescar() {
    try {
      setEstado(await estadoRender());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo consultar el estado de Render");
    }
  }

  useEffect(() => {
    refrescar();
  }, []);

  async function conectar() {
    setConectando(true);
    setError(null);
    try {
      setEstado(await conectarRender(apiKey));
      setApiKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo conectar con Render");
    } finally {
      setConectando(false);
    }
  }

  async function desconectar() {
    try {
      await desconectarRender();
      await refrescar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo desconectar");
    }
  }

  return (
    <div className="tarjeta-conexion">
      <div className="cabecera-conexion">
        <strong>Render</strong>
        <span className={`pastilla ${estado?.conectado ? "viva" : ""}`}>
          {estado?.conectado ? "Conectado" : "No conectado"}
        </span>
      </div>

      {estado?.conectado && (
        <p className="apagado" style={{ margin: "0.35rem 0" }}>
          {estado.email && <>Cuenta: {estado.email}. </>}
          {estado.servicio_url ? (
            <>
              Servicio: <a href={estado.servicio_url}>{estado.servicio_url}</a>
              {estado.servicio_suspendido === "suspended" && " (suspendido)"}
            </>
          ) : (
            "No se encontró un servicio con el nombre configurado (RENDER_SERVICE_NAME)."
          )}
        </p>
      )}

      {estado?.advertencia && <p className="error">{estado.advertencia}</p>}
      {error && <p className="error">{error}</p>}

      <div className="fila-alta" style={{ marginTop: "0.5rem" }}>
        {estado?.conectado ? (
          <button onClick={desconectar}>Desconectar</button>
        ) : (
          <>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="API key de Render"
              aria-label="API key de Render"
            />
            <button
              className="primario"
              onClick={conectar}
              disabled={conectando || !apiKey.trim()}
            >
              {conectando ? "Verificando…" : "Conectar"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
