"use client";

import Link from "next/link";
import type { CasoDeUso, ResumenCorrida } from "@/lib/types";

/** Matiz del ícono de cada proyecto — mismo criterio de color que ya usan las tarjetas de agente. */
const MATIZ_PROYECTO: Record<string, string> = {
  items: "var(--orchestrator)",
  calculadora: "var(--backend)",
  leads_zapatillas: "var(--frontend)",
  encuesta: "var(--deploy)",
};

function estadoProyecto(id: string, resumen: ResumenCorrida | null): { texto: string; clase: string } {
  const esElActivo = resumen != null && (resumen.caso_de_uso ?? "items") === id;
  if (!esElActivo) return { texto: "Sin ejecutar todavía", clase: "" };
  if (resumen!.status === "running") return { texto: "Ejecutándose ahora…", clase: "corriendo" };
  if (resumen!.status === "error") return { texto: "Última corrida con errores", clase: "error" };
  return { texto: "Última corrida completa", clase: "done" };
}

/**
 * Los casos de prueba se listan como "proyectos" — una fila por caso, con su
 * ícono, nombre y descripción, al estilo de la galería de proyectos de
 * Claude/ChatGPT. Cada fila abre la página propia del proyecto; lanzar la
 * corrida y ver el progreso pasa ahí, no en esta lista.
 */
export default function ListaProyectos({
  proyectos,
  resumen,
}: {
  proyectos: CasoDeUso[];
  resumen: ResumenCorrida | null;
}) {
  return (
    <div className="lista-proyectos" role="list" aria-label="Proyectos">
      {proyectos.map((p) => {
        const estado = estadoProyecto(p.id, resumen);
        return (
          <Link key={p.id} href={`/proyectos/${p.id}`} className="fila-proyecto" role="listitem">
            <span className="icono-proyecto" style={{ ["--matiz" as string]: MATIZ_PROYECTO[p.id] }} aria-hidden>
              {p.icono}
            </span>
            <span className="info-proyecto">
              <strong>{p.nombre}</strong>
              <span className="descripcion-proyecto">{p.descripcion}</span>
            </span>
            <span className={`estado-proyecto ${estado.clase}`}>{estado.texto}</span>
            <span className="chevron-proyecto" aria-hidden>
              ›
            </span>
          </Link>
        );
      })}
      {proyectos.length === 0 && <p className="apagado sin-proyectos">Cargando proyectos…</p>}

      <Link href="/proyectos/nuevo" className="fila-proyecto fila-nuevo-proyecto">
        <span className="icono-proyecto icono-nuevo-proyecto" aria-hidden>
          +
        </span>
        <span className="info-proyecto">
          <strong>Nuevo proyecto</strong>
          <span className="descripcion-proyecto">
            Importá una especificación y convertila en tareas del backlog
          </span>
        </span>
        <span className="chevron-proyecto" aria-hidden>
          ›
        </span>
      </Link>
    </div>
  );
}
