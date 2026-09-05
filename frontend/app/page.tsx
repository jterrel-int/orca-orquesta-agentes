"use client";

import Link from "next/link";
import { useMemo } from "react";
import AgentCard from "@/components/AgentCard";
import EstadoSistema from "@/components/EstadoSistema";
import LogStream from "@/components/LogStream";
import RunButton from "@/components/RunButton";
import { useEventos } from "@/lib/ws";
import { AGENTES, type EstadoAgente, type EventoAgente } from "@/lib/types";

/**
 * El estado de cada agente se deriva del stream de eventos, no de un sondeo al
 * backend. El WebSocket ya trae todo lo necesario; un GET periódico solo
 * agregaría otra fuente de verdad que puede contradecir a la primera.
 */
function derivarEstados(eventos: EventoAgente[]) {
  const mapa = new Map<string, { status: EstadoAgente; ultimo: string }>();
  for (const nombre of AGENTES) mapa.set(nombre, { status: "pending", ultimo: "" });
  for (const e of eventos) {
    if (!mapa.has(e.agent)) continue;
    mapa.set(e.agent, { status: e.status, ultimo: e.msg });
  }
  return mapa;
}

export default function Panel() {
  const { eventos, conexion } = useEventos();
  const estados = useMemo(() => derivarEstados(eventos), [eventos]);

  const corriendo = useMemo(() => {
    const ultimoOrq = [...eventos].reverse().find((e) => e.agent === "orchestrator");
    return ultimoOrq?.status === "running";
  }, [eventos]);

  return (
    <>
      <header className="cabecera">
        <h1>Orquesta</h1>
        <span className="sub">panel de agentes</span>
        <div className="derecha">
          <nav className="nav">
            <Link href="/items">Items</Link>
          </nav>
          <span
            className={`pastilla ${conexion === "conectado" ? "viva" : conexion === "desconectado" ? "muerta" : ""}`}
          >
            {conexion === "conectado" ? "WS conectado" : conexion === "conectando" ? "conectando…" : "WS caído"}
          </span>
        </div>
      </header>

      <main className="contenido">
        <EstadoSistema />

        <div style={{ marginBottom: "1.25rem" }}>
          <RunButton activo={corriendo} />
        </div>

        <section className="rejilla-agentes" aria-label="Estado por agente">
          {AGENTES.map((nombre) => {
            const est = estados.get(nombre)!;
            return (
              <AgentCard
                key={nombre}
                agente={nombre}
                status={est.status}
                ultimo={est.ultimo}
              />
            );
          })}
        </section>

        <h2 style={{ fontSize: "0.95rem", margin: "0 0 0.6rem" }}>Logs en vivo</h2>
        <LogStream eventos={eventos} />
      </main>
    </>
  );
}
