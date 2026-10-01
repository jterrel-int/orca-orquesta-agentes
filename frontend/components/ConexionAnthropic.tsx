"use client";

import { useEffect, useState } from "react";
import {
  conectarAnthropic,
  desconectarAnthropic,
  estadoAnthropic,
  establecerLimiteAnthropic,
} from "@/lib/api";
import type { EstadoAnthropic } from "@/lib/types";

export default function ConexionAnthropic() {
  const [estado, setEstado] = useState<EstadoAnthropic | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [conectando, setConectando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limiteInput, setLimiteInput] = useState("");
  const [guardandoLimite, setGuardandoLimite] = useState(false);

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

  async function guardarLimite() {
    const tokens = Number(limiteInput);
    if (!Number.isFinite(tokens) || tokens <= 0) return;
    setGuardandoLimite(true);
    setError(null);
    try {
      const uso = await establecerLimiteAnthropic(tokens);
      setEstado((actual) => (actual ? { ...actual, uso } : actual));
      setLimiteInput("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el límite de tokens");
    } finally {
      setGuardandoLimite(false);
    }
  }

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
        Esta es una API key de console.anthropic.com (se factura por token) — no tiene relación
        con haber iniciado sesión en claude.ai o en Claude Code en esta máquina; Anthropic no
        ofrece una forma de reutilizar esa sesión acá, así que hace falta generar una key aparte.
        Con esta key conectada, el CRUD de Items, los 3 casos de prueba y la generación de tareas
        desde un documento pasan a usar un modelo real en vez de la división guionada.
      </p>

      {estado?.conectado && (
        <>
          <p className="apagado" style={{ margin: "0.35rem 0" }}>
            Modelo: <span className="mono">{estado.modelo}</span> · Key:{" "}
            <span className="mono">{estado.clave}</span>
          </p>

          <p className="apagado" style={{ margin: "0.35rem 0", fontSize: "0.85rem" }}>
            Esto no es el gasto real de tu cuenta de Anthropic — eso no es consultable con una API
            key normal — sino un contador propio de Orquesta contra un límite de tokens que vos
            definís, para saber cuándo frenar. Te avisamos por toast cada 10% que subas.
          </p>

          {estado.uso ? (
            <div style={{ margin: "0.5rem 0" }}>
              <div
                className="fila-alta"
                style={{ justifyContent: "space-between", marginBottom: "0.3rem" }}
              >
                <span style={{ fontSize: "0.85rem" }}>
                  {estado.uso.tokens_usados.toLocaleString("es")} /{" "}
                  {estado.uso.limite_tokens.toLocaleString("es")} tokens
                </span>
                <strong style={{ fontSize: "0.85rem" }}>
                  {estado.uso.porcentaje.toFixed(1)}%
                </strong>
              </div>
              <div className="barra-uso">
                <div
                  className={`barra-uso-relleno ${
                    estado.uso.porcentaje >= 90
                      ? "critico"
                      : estado.uso.porcentaje >= 70
                        ? "alerta"
                        : ""
                  }`}
                  style={{ width: `${Math.min(100, estado.uso.porcentaje)}%` }}
                />
              </div>
            </div>
          ) : (
            <p className="apagado" style={{ margin: "0.35rem 0", fontSize: "0.85rem" }}>
              Todavía no definiste un límite de tokens.
            </p>
          )}

          <div className="fila-alta" style={{ marginTop: "0.4rem" }}>
            <input
              type="number"
              min={1}
              value={limiteInput}
              onChange={(e) => setLimiteInput(e.target.value)}
              placeholder={estado.uso ? "Nuevo límite de tokens" : "Límite de tokens (ej: 1000000)"}
              aria-label="Límite de tokens de Anthropic"
              style={{ maxWidth: "12rem" }}
            />
            <button
              type="button"
              onClick={guardarLimite}
              disabled={guardandoLimite || !limiteInput.trim()}
            >
              {guardandoLimite ? "Guardando…" : estado.uso ? "Actualizar límite" : "Guardar límite"}
            </button>
          </div>
        </>
      )}

      {error && <p className="error">{error}</p>}

      <div className="fila-alta" style={{ marginTop: "0.5rem" }}>
        {estado?.conectado ? (
          <button onClick={desconectar}>Desconectar</button>
        ) : (
          <>
            <button
              type="button"
              onClick={() =>
                window.open("https://console.anthropic.com/settings/keys", "_blank", "noreferrer")
              }
            >
              Generar key en console.anthropic.com ↗
            </button>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Pegá acá la key (sk-ant-…)"
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
