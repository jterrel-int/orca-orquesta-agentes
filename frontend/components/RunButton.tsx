"use client";

import { useState } from "react";
import { lanzarCorrida } from "@/lib/api";

export default function RunButton({
  activo,
  onLanzada,
}: {
  activo: boolean;
  onLanzada?: () => void;
}) {
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ejecutar() {
    setEnviando(true);
    setError(null);
    try {
      await lanzarCorrida();
      onLanzada?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo lanzar la corrida");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fila-alta">
      <button className="primario" onClick={ejecutar} disabled={enviando || activo}>
        {activo ? "Agentes en ejecución…" : "Ejecutar agentes"}
      </button>
      {error && <span className="error">{error}</span>}
    </div>
  );
}
