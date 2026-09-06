"use client";

import { useState } from "react";
import Link from "next/link";
import { lanzarCorrida } from "@/lib/api";
import type { CasoDeUso } from "@/lib/types";

interface Props {
  caso: CasoDeUso;
  /** Hay una corrida en curso (de cualquier caso): deshabilita todos los botones. */
  corriendo: boolean;
  /** Esta card es la que está corriendo (por click propio o por lo que confirma el backend). */
  activa: boolean;
  /** La última corrida terminó bien y era de este caso: mostrar el link de resultado. */
  mostrarResultado: boolean;
  rutaResultado: string;
  onLanzada: (id: string) => void;
}

export default function CasoDePruebaCard({
  caso,
  corriendo,
  activa,
  mostrarResultado,
  rutaResultado,
  onLanzada,
}: Props) {
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ejecutar() {
    setEnviando(true);
    setError(null);
    onLanzada(caso.id);
    try {
      await lanzarCorrida(caso.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo lanzar la corrida");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <article className={`tarjeta-caso ${activa ? "activa" : ""}`}>
      <span className="icono-caso" aria-hidden>
        {caso.icono}
      </span>
      <h3>{caso.nombre}</h3>
      <p className="descripcion-caso">{caso.descripcion}</p>

      {error && <p className="error">{error}</p>}

      <div className="pie-caso">
        <button onClick={ejecutar} disabled={enviando || corriendo}>
          {activa ? "Ejecutando…" : "Ejecutar"}
        </button>
        {mostrarResultado && (
          <Link className="enlace-resultado" href={rutaResultado}>
            Ver resultado →
          </Link>
        )}
      </div>
    </article>
  );
}
