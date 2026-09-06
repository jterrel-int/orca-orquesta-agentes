"use client";

import { useEffect, useRef, useState } from "react";
import type { EventoAgente } from "@/lib/types";

function hora(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime())
    ? "--:--:--"
    : d.toLocaleTimeString("es-PE", { hour12: false });
}

export default function LogStream({ eventos }: { eventos: EventoAgente[] }) {
  const finRef = useRef<HTMLDivElement>(null);
  const cajaRef = useRef<HTMLDivElement>(null);
  const [pegadoAbajo, setPegadoAbajo] = useState(true);

  // Autoscroll solo si el usuario ya estaba al final. Si subió a leer algo,
  // no se le arrastra la vista con cada evento nuevo.
  useEffect(() => {
    if (pegadoAbajo) finRef.current?.scrollIntoView({ block: "end" });
  }, [eventos, pegadoAbajo]);

  function alDesplazar() {
    const caja = cajaRef.current;
    if (!caja) return;
    const margen = caja.scrollHeight - caja.scrollTop - caja.clientHeight;
    setPegadoAbajo(margen < 40);
  }

  if (eventos.length === 0) {
    return (
      <div className="consola">
        <p className="consola-vacia">
          Sin eventos. Ejecutá un caso de prueba y los logs aparecerán aquí en
          vivo.
        </p>
      </div>
    );
  }

  return (
    <div className="consola log" ref={cajaRef} onScroll={alDesplazar} role="log" aria-live="polite">
      {eventos.map((e, i) => (
        <div
          key={`${e.ts}-${i}`}
          className={`linea ${e.status}`}
          style={{ ["--matiz" as string]: `var(--${e.agent}, var(--apagado))` }}
        >
          <span className="hora">{hora(e.ts)}</span>
          <span className="quien">{e.agent}</span>
          <span className="texto">{e.msg}</span>
        </div>
      ))}
      <div ref={finRef} />
    </div>
  );
}
