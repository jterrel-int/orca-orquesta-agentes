"use client";

import { useMemo } from "react";
import { ETAPAS_FABRICA, agentesVivos } from "@/lib/fabrica";
import type { ConfigFabrica, Encargo, EventoAgente } from "@/lib/types";

export default function PortadaFabrica({
  eventos,
  encargos,
  config,
}: {
  eventos: EventoAgente[];
  encargos: Encargo[];
  config: ConfigFabrica | null;
}) {
  const corriendo = useMemo(
    () => new Set(encargos.filter((e) => e.corriendo).map((e) => e.id)),
    [encargos],
  );
  const vivos = useMemo(() => agentesVivos(eventos, corriendo), [eventos, corriendo]);
  const total = [...vivos.values()].reduce((a, b) => a + b, 0);
  const encargosCorriendo = corriendo.size;
  const especsEnCurso = encargos.reduce(
    (n, e) => n + e.especificaciones.filter((s) => s.estado === "en_curso").length,
    0,
  );

  return (
    <section className={`portada-fabrica ${total > 0 ? "en-marcha" : ""}`}>
      <div className="portada-texto">
        <span className="sobretitulo">Fábrica de software agéntica</span>
        <h2>
          Muchos agentes, <em>al mismo tiempo</em>.
        </h2>
        <p>
          El Líder parte cada pedido en especificaciones y construye en paralelo todas las que no
          dependen entre sí. Cada encargo corre por su cuenta, así que varios pedidos avanzan a la vez.
        </p>
        <div className="fila-pastillas">
          <span className="chip-config">⇉ hasta {config?.paralelismo ?? "…"} especificaciones a la vez</span>
          <span className="chip-config">
            {config?.orquestador === "prefect" ? "Prefect + asyncio" : "asyncio"}
          </span>
          <span className="chip-config">aprobación humana: {config?.aprobacion_humana ?? "…"}</span>
          {config?.cache_llm && <span className="chip-config">caché de LLM activa</span>}
        </div>
      </div>

      <div className="portada-numeros">
        <div className="numero-grande">
          <strong className="mono">{total}</strong>
          <span>{total === 1 ? "agente trabajando ahora" : "agentes trabajando ahora"}</span>
        </div>
        <div className="numeros-chicos">
          <div>
            <strong className="mono">{encargosCorriendo}</strong>
            <span>{encargosCorriendo === 1 ? "encargo en marcha" : "encargos en marcha"}</span>
          </div>
          <div>
            <strong className="mono">{especsEnCurso}</strong>
            <span>
              {especsEnCurso === 1 ? "especificación en construcción" : "especificaciones en construcción"}
            </span>
          </div>
        </div>
        <ul className="enjambre" aria-label="Instancias por agente">
          {ETAPAS_FABRICA.map((etapa) => {
            const n = vivos.get(etapa.agente) ?? 0;
            return (
              <li key={etapa.agente} className={n > 0 ? "vivo" : ""}>
                <span className="enjambre-puntos" aria-hidden>
                  {Array.from({ length: Math.max(1, Math.min(n, 6)) }, (_, i) => (
                    <i key={i} style={{ animationDelay: `${i * 0.18}s` }} />
                  ))}
                </span>
                <span>{etapa.etiqueta}</span>
                <strong className="mono">{n}</strong>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
