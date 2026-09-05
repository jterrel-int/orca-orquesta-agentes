"use client";

import { useState, type FormEvent } from "react";
import { agregarTareaBacklog } from "@/lib/api";
import type { LadoBacklog, TareaBacklog } from "@/lib/types";

export default function FormularioTarea({
  onCreada,
}: {
  onCreada: (tarea: TareaBacklog) => void;
}) {
  const [titulo, setTitulo] = useState("");
  const [cuerpo, setCuerpo] = useState("");
  const [lado, setLado] = useState<LadoBacklog>("BE");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const creada = await agregarTareaBacklog({ titulo, cuerpo, lado });
      onCreada(creada);
      setTitulo("");
      setCuerpo("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo agregar la tarea");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="form-tarea" onSubmit={enviar}>
      <div className="fila-alta">
        <select
          value={lado}
          onChange={(e) => setLado(e.target.value as LadoBacklog)}
          aria-label="Lado"
        >
          <option value="BE">Backend</option>
          <option value="FE">Frontend</option>
        </select>
        <input
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          placeholder="Título de la tarea"
          aria-label="Título"
          required
        />
      </div>
      <textarea
        value={cuerpo}
        onChange={(e) => setCuerpo(e.target.value)}
        placeholder="Qué hay que hacer, qué archivos toca, cómo se verifica…"
        aria-label="Descripción"
        rows={4}
        required
      />
      <div className="fila-alta">
        <button
          className="primario"
          type="submit"
          disabled={enviando || !titulo.trim() || !cuerpo.trim()}
        >
          {enviando ? "Agregando…" : "Agregar al backlog"}
        </button>
        {error && <span className="error">{error}</span>}
      </div>
    </form>
  );
}
