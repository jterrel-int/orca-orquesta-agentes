"use client";

import { useEffect, useState } from "react";
import FormularioTarea from "@/components/FormularioTarea";
import { listarBacklog } from "@/lib/api";
import type { TareaBacklog } from "@/lib/types";

export default function PaginaBacklog() {
  const [tareas, setTareas] = useState<TareaBacklog[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarBacklog()
      .then(setTareas)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "No se pudo cargar"))
      .finally(() => setCargando(false));
  }, []);

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
        {!cargando && !error && tareas.length === 0 && (
          <p className="apagado">No hay tareas en el backlog todavía.</p>
        )}

        <div className="rejilla-tareas">
          {tareas.map((t) => (
            <article key={t.id} className="tarjeta-tarea">
              <div className="cabecera-tarea">
                <span className={`pastilla-lado ${t.lado === "BE" ? "backend" : "frontend"}`}>
                  {t.id}
                </span>
                <h3>{t.titulo}</h3>
              </div>
              <div className="cuerpo-tarea">{t.cuerpo}</div>
            </article>
          ))}
        </div>
      </main>
    </>
  );
}
