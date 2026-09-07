"use client";

import { useEffect, useState } from "react";
import FormularioTarea from "@/components/FormularioTarea";
import { listarBacklog } from "@/lib/api";
import { partirCuerpoTarea } from "@/lib/backlog";
import type { LadoBacklog, TareaBacklog } from "@/lib/types";

type Pestana = "todas" | LadoBacklog;

const PESTANAS: { valor: Pestana; etiqueta: string }[] = [
  { valor: "todas", etiqueta: "Todas" },
  { valor: "BE", etiqueta: "Backend" },
  { valor: "FE", etiqueta: "Frontend" },
  { valor: "DE", etiqueta: "Deploy" },
];

const MATIZ_LADO: Record<LadoBacklog, string> = {
  BE: "var(--backend)",
  FE: "var(--frontend)",
  DE: "var(--deploy)",
};

const CLASE_LADO: Record<LadoBacklog, string> = {
  BE: "backend",
  FE: "frontend",
  DE: "deploy",
};

export default function PaginaBacklog() {
  const [tareas, setTareas] = useState<TareaBacklog[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Pestana>("todas");

  useEffect(() => {
    listarBacklog()
      .then(setTareas)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "No se pudo cargar"))
      .finally(() => setCargando(false));
  }, []);

  const tareasFiltradas = tareas.filter((t) => tab === "todas" || t.lado === tab);

  return (
    <>
      <header className="cabecera">
        <h1>Backlog</h1>
        <span className="sub">docs/BACKLOG.md — tareas que un agente toma con /tarea</span>
      </header>

      <main className="contenido">
        <FormularioTarea onCreada={(t) => setTareas((prev) => [...prev, t])} />

        {cargando && <p className="apagado">Cargando…</p>}
        {error && <p className="error">{error}</p>}

        {!cargando && !error && (
          <>
            <div className="tabs-lado" role="tablist" aria-label="Filtrar por frente">
              {PESTANAS.map((p) => (
                <button
                  key={p.valor}
                  type="button"
                  role="tab"
                  aria-selected={tab === p.valor}
                  className={tab === p.valor ? "activo" : ""}
                  onClick={() => setTab(p.valor)}
                >
                  {p.etiqueta}
                </button>
              ))}
            </div>

            {tareas.length === 0 && <p className="apagado">No hay tareas en el backlog todavía.</p>}
            {tareas.length > 0 && tareasFiltradas.length === 0 && (
              <p className="apagado">No hay tareas para este frente.</p>
            )}

            <div className="rejilla-tareas">
              {tareasFiltradas.map((t) => (
                <article
                  key={t.id}
                  className="tarjeta-tarea"
                  style={{ ["--matiz" as string]: MATIZ_LADO[t.lado] }}
                >
                  <div className="cabecera-tarea">
                    <span className={`pastilla-lado ${CLASE_LADO[t.lado]}`}>
                      {t.id}
                    </span>
                    <h3>{t.titulo}</h3>
                  </div>
                  <div className="cuerpo-tarea">
                    {partirCuerpoTarea(t.cuerpo).map((seccion, i) => (
                      <div className="subseccion-tarea" key={`${t.id}-${i}`}>
                        {seccion.titulo && <span className="etiqueta-subseccion">{seccion.titulo}</span>}
                        <p className="texto-subseccion">{seccion.texto}</p>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </main>
    </>
  );
}
