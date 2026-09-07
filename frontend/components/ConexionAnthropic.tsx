"use client";

import { useEffect, useState } from "react";
import { conectarAnthropic, desconectarAnthropic, estadoAnthropic } from "@/lib/api";
import type { EstadoAnthropic } from "@/lib/types";

export default function ConexionAnthropic() {
  const [estado, setEstado] = useState<EstadoAnthropic | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [conectando, setConectando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refrescar() {
    try {
      setEstado(await estadoAnthropic());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo consultar el estado de Anthropic");
    }
  }

  useEffect(() => {
    refrescar();
  }, []);

  async function conectar() {
    setConectando(true);
    setError(null);
    try {
      setEstado(await conectarAnthropic(apiKey));
      setApiKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo conectar con Anthropic");
    } finally {
      setConectando(false);
    }
  }

  async function desconectar() {
    try {
      await desconectarAnthropic();
      await refrescar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo desconectar");
    }
  }

  return (
    <div className="tarjeta-conexion">
      <div className="cabecera-conexion">
        <strong>Anthropic (IA real)</strong>
        <span className={`pastilla ${estado?.conectado ? "viva" : ""}`}>
          {estado?.conectado ? "Conectado" : "No conectado"}
        </span>
      </div>

      <p className="apagado" style={{ margin: "0.35rem 0", fontSize: "0.85rem" }}>
        Esta es una API key de{" "}
        <a href="https://console.anthropic.com" target="_blank" rel="noreferrer">
          console.anthropic.com
        </a>{" "}
        (se factura por token) — no tiene relación con haber iniciado sesión en claude.ai o en
        Claude Code en esta máquina; no hay forma de reutilizar esa sesión acá. Con esta key
        conectada, el CRUD de Items, los 3 casos de prueba y la generación de tareas desde un
        documento pasan a usar un modelo real en vez de la división guionada.
      </p>

      {estado?.conectado && (
        <p className="apagado" style={{ margin: "0.35rem 0" }}>
          Modelo: <span className="mono">{estado.modelo}</span> · Key: <span className="mono">{estado.clave}</span>
        </p>
      )}

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
              placeholder="sk-ant-…"
              aria-label="API key de Anthropic"
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
