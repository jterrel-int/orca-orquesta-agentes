"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AgentCard from "@/components/AgentCard";
import LogStream from "@/components/LogStream";
import { casosDeUso, estadoCorrida, lanzarCorrida } from "@/lib/api";
import { useEventos } from "@/lib/ws";
import { AGENTES, type CasoDeUso, type EstadoAgente, type EventoAgente, type ResumenCorrida } from "@/lib/types";

/** Dónde escribe FrontendAgent el componente de cada caso — ver casos_de_uso.py::destino_frontend. */
const RUTA_RESULTADO: Record<string, string> = {
  items: "/items",
  calculadora: "/casos/calculadora",
  leads_zapatillas: "/casos/leads_zapatillas",
  encuesta: "/casos/encuesta",
};

function derivarEstados(eventos: EventoAgente[]) {
  const mapa = new Map<string, { status: EstadoAgente; ultimo: string }>();
  for (const nombre of AGENTES) mapa.set(nombre, { status: "pending", ultimo: "" });
  for (const e of eventos) {
    if (!mapa.has(e.agent)) continue;
    mapa.set(e.agent, { status: e.status, ultimo: e.msg });
  }
  return mapa;
}

export default function PaginaProyecto({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { eventos } = useEventos();
  const estados = useMemo(() => derivarEstados(eventos), [eventos]);

  const [casos, setCasos] = useState<CasoDeUso[]>([]);
  const [resumen, setResumen] = useState<ResumenCorrida | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    casosDeUso()
      .then(setCasos)
      .catch(() => {});
  }, []);

  useEffect(() => {
    estadoCorrida()
      .then(setResumen)
      .catch(() => {});
  }, [eventos.length]);

  const proyecto = casos.find((c) => c.id === id);

  const corriendo = useMemo(() => {
    const ultimoOrq = [...eventos].reverse().find((e) => e.agent === "orchestrator");
    return ultimoOrq?.status === "running" || resumen?.status === "running";
  }, [eventos, resumen]);

  const esteEsElActivo = (resumen?.caso_de_uso ?? "items") === id;
  const mostrarProgreso = corriendo && esteEsElActivo;
  const mostrarResultado = resumen?.status === "done" && esteEsElActivo;

  async function ejecutar() {
    setEnviando(true);
    setError(null);
    try {
      await lanzarCorrida(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo lanzar la corrida");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <header className="cabecera">
        <Link href="/" className="volver-proyectos">
          ← Proyectos
        </Link>
        <h1>
          {proyecto ? `${proyecto.icono} ${proyecto.nombre}` : "Proyecto"}
        </h1>
        <span className="sub">{proyecto?.descripcion ?? "Cargando…"}</span>
      </header>

      <main className="contenido">
        <div className="fila-alta" style={{ marginBottom: "1.25rem" }}>
          <button
            className="primario"
            onClick={ejecutar}
            disabled={enviando || corriendo || !proyecto}
          >
            {mostrarProgreso ? "Ejecutando…" : "Ejecutar"}
          </button>
          {corriendo && !esteEsElActivo && (
            <span className="apagado">Hay otra corrida en curso; esperá a que termine.</span>
          )}
          {error && <span className="error">{error}</span>}
          {mostrarResultado && (
            <Link className="enlace-resultado" href={RUTA_RESULTADO[id] ?? "/"}>
              Ver resultado →
            </Link>
          )}
        </div>

        {(mostrarProgreso || mostrarResultado) && (
          <>
            <section className="rejilla-agentes" aria-label="Estado por agente">
              {AGENTES.map((nombre) => {
                const est = estados.get(nombre)!;
                return <AgentCard key={nombre} agente={nombre} status={est.status} ultimo={est.ultimo} />;
              })}
            </section>

            <h2 style={{ fontSize: "0.95rem", margin: "0 0 0.6rem" }}>Logs en vivo</h2>
            <LogStream eventos={eventos} />
          </>
        )}

        {!mostrarProgreso && !mostrarResultado && (
          <p className="apagado">
            Todavía no corriste este proyecto. Apretá "Ejecutar" para ver a los tres agentes trabajar.
          </p>
        )}
      </main>
    </>
  );
}
