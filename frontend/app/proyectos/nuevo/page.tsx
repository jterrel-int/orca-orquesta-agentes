"use client";

import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { generarTareasDesdeEspecificacion, type AlcanceGeneracion } from "@/lib/api";
import type { TareaBacklog } from "@/lib/types";

const ALCANCES: { valor: AlcanceGeneracion; etiqueta: string }[] = [
  { valor: "BE", etiqueta: "Backend" },
  { valor: "FE", etiqueta: "Frontend" },
  { valor: "todo", etiqueta: "Todo (back + front)" },
];

const FORMATOS_ACEPTADOS = ".txt,.md,.pdf,.docx";

export default function NuevoProyecto() {
  const [alcance, setAlcance] = useState<AlcanceGeneracion>("todo");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creadas, setCreadas] = useState<TareaBacklog[] | null>(null);
  const inputArchivo = useRef<HTMLInputElement>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    setCreadas(null);
    try {
      const tareas = await generarTareasDesdeEspecificacion({ alcance, archivo, texto });
      setCreadas(tareas);
      setTexto("");
      setArchivo(null);
      if (inputArchivo.current) inputArchivo.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron generar las tareas");
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
        <h1>Nuevo proyecto</h1>
        <span className="sub">importá una especificación y convertila en tareas del backlog</span>
      </header>

      <main className="contenido">
        <p className="apagado" style={{ maxWidth: "56ch", marginTop: 0 }}>
          Esto no lanza una corrida de agentes como las otras tarjetas de Proyectos: lee tu
          documento (o el texto que pegues) y lo convierte en varias tareas nuevas en el{" "}
          <Link href="/backlog">Backlog</Link>, listas para que un agente las tome después.
        </p>

        <form className="form-tarea" onSubmit={enviar}>
          <div className="tabs-lado" role="tablist" aria-label="A qué frente pertenece">
            {ALCANCES.map((a) => (
              <button
                key={a.valor}
                type="button"
                role="tab"
                aria-selected={alcance === a.valor}
                className={alcance === a.valor ? "activo" : ""}
                onClick={() => setAlcance(a.valor)}
              >
                {a.etiqueta}
              </button>
            ))}
          </div>

          <label className="etiqueta-campo" htmlFor="archivo-spec">
            Documento de especificación (.txt, .md, .pdf, .docx)
          </label>
          <input
            id="archivo-spec"
            ref={inputArchivo}
            type="file"
            accept={FORMATOS_ACEPTADOS}
            onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
          />

          <label className="etiqueta-campo" htmlFor="texto-spec">
            …o pegá el texto directamente
          </label>
          <textarea
            id="texto-spec"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Pegá acá la especificación funcional/técnica si no tenés un archivo a mano…"
            rows={6}
            disabled={!!archivo}
          />

          <div className="fila-alta">
            <button
              className="primario"
              type="submit"
              disabled={enviando || (!archivo && texto.trim().length < 30)}
            >
              {enviando ? "Generando tareas…" : "Generar tareas"}
            </button>
            {error && <span className="error">{error}</span>}
          </div>
        </form>

        {creadas && creadas.length > 0 && (
          <section className="resultado-generacion">
            <h2 style={{ fontSize: "0.95rem", margin: "0 0 0.6rem" }}>
              {creadas.length} tarea{creadas.length === 1 ? "" : "s"} agregada
              {creadas.length === 1 ? "" : "s"} al backlog
            </h2>
            <ul className="lista-tareas-generadas">
              {creadas.map((t) => (
                <li key={t.id}>
                  <span className={`pastilla-lado ${t.lado === "BE" ? "backend" : "frontend"}`}>
                    {t.id}
                  </span>
                  {t.titulo}
                </li>
              ))}
            </ul>
            <Link className="enlace-resultado" href="/backlog">
              Ver en el Backlog →
            </Link>
          </section>
        )}
      </main>
    </>
  );
}
