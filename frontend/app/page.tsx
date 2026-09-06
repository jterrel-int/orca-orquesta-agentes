"use client";

import { useEffect, useMemo, useState } from "react";
import AgentCard from "@/components/AgentCard";
import CasoDePruebaCard from "@/components/CasoDePruebaCard";
import EstadoSistema from "@/components/EstadoSistema";
import LogStream from "@/components/LogStream";
import { casosDeUso, estadoCorrida } from "@/lib/api";
import { useEventos } from "@/lib/ws";
import { AGENTES, type CasoDeUso, type EstadoAgente, type EventoAgente, type ResumenCorrida } from "@/lib/types";

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

/** Dónde escribe FrontendAgent el componente de cada caso — ver casos_de_uso.py::destino_frontend. */
const RUTA_RESULTADO: Record<string, string> = {
  items: "/items",
  calculadora: "/casos/calculadora",
  leads_zapatillas: "/casos/leads_zapatillas",
  encuesta: "/casos/encuesta",
};

export default function Panel() {
  const { eventos, conexion } = useEventos();
  const estados = useMemo(() => derivarEstados(eventos), [eventos]);

  const [casos, setCasos] = useState<CasoDeUso[]>([]);
  const [resumen, setResumen] = useState<ResumenCorrida | null>(null);
  const [casoSolicitado, setCasoSolicitado] = useState<string | null>(null);

  useEffect(() => {
    casosDeUso()
      .then(setCasos)
      .catch(() => {
        // Si no responde, la pastilla de WS/salud ya avisa que algo anda mal.
      });
  }, []);

  // Se reconsulta con cada evento nuevo: durante una corrida llegan seguido,
  // así que el estado de la corrida (incluido su caso_de_uso) se mantiene al día.
  useEffect(() => {
    estadoCorrida()
      .then(setResumen)
      .catch(() => {});
  }, [eventos.length]);

  const corriendo = useMemo(() => {
    const ultimoOrq = [...eventos].reverse().find((e) => e.agent === "orchestrator");
    return ultimoOrq?.status === "running" || resumen?.status === "running";
  }, [eventos, resumen]);

  // Cuál caso resaltar como "corriendo": lo que se pidió recién (para reaccionar
  // al instante) o, si ya llegó, lo que confirma el backend.
  const casoActivo = resumen?.status === "running" ? resumen.caso_de_uso ?? "items" : casoSolicitado;

  return (
    <>
      <header className="cabecera">
        <h1>Panel</h1>
        <span className="sub">ejecución de agentes en vivo</span>
        <div className="derecha">
          <span
            className={`pastilla ${conexion === "conectado" ? "viva" : conexion === "desconectado" ? "muerta" : ""}`}
          >
            {conexion === "conectado" ? "WS conectado" : conexion === "conectando" ? "conectando…" : "WS caído"}
          </span>
        </div>
      </header>

      <main className="contenido">
        <EstadoSistema />

        <h2 style={{ fontSize: "0.95rem", margin: "0 0 0.6rem" }}>Casos de prueba</h2>
        <section className="rejilla-casos" aria-label="Casos de prueba">
          {casos.map((caso) => (
            <CasoDePruebaCard
              key={caso.id}
              caso={caso}
              corriendo={corriendo}
              activa={corriendo && casoActivo === caso.id}
              mostrarResultado={
                resumen?.status === "done" && (resumen.caso_de_uso ?? "items") === caso.id
              }
              rutaResultado={RUTA_RESULTADO[caso.id] ?? "/"}
              onLanzada={setCasoSolicitado}
            />
          ))}
        </section>

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
