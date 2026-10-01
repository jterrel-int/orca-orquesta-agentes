"use client";

import { useMemo } from "react";
import { ETAPAS_ESPEC, ETIQUETA_ESPEC, claseEncargo, derivarCarriles, nivelesDe } from "@/lib/fabrica";
import type { Especificacion, EventoAgente } from "@/lib/types";

/**
 * Una fila por especificación, agrupadas por nivel del grafo: las de un mismo
 * nivel no dependen entre sí y el Líder las construye a la vez. Cada celda es
 * una etapa; la que está corriendo late.
 */
export default function CarrilesParalelos({
  especificaciones,
  eventos,
  paralelismo,
  vivo,
}: {
  especificaciones: Especificacion[];
  eventos: EventoAgente[];
  paralelismo: number;
  vivo: boolean;
}) {
  const niveles = useMemo(() => nivelesDe(especificaciones), [especificaciones]);
  const carriles = useMemo(
    () => derivarCarriles(eventos, especificaciones.map((e) => e.id), vivo),
    [eventos, especificaciones, vivo],
  );

  const grupos = useMemo(() => {
    const porNivel = new Map<number, Especificacion[]>();
    for (const e of especificaciones) {
      const n = niveles.get(e.id) ?? 1;
      porNivel.set(n, [...(porNivel.get(n) ?? []), e]);
    }
    return [...porNivel.entries()].sort(([a], [b]) => a - b);
  }, [especificaciones, niveles]);

  const activas = [...carriles.values()].filter((c) => c.activo).length;

  if (especificaciones.length === 0) return null;

  return (
    <section className="carriles" aria-label="Especificaciones construyéndose en paralelo">
      <div className="carriles-cabecera">
        <div>
          <span className="etiqueta-subseccion">Construcción en paralelo</span>
          <p className="carriles-resumen">
            <strong className="mono">{activas}</strong> de {especificaciones.length} especificaciones
            trabajando ahora · hasta <strong className="mono">{paralelismo}</strong> a la vez por nivel
          </p>
        </div>
        <div className="leyenda-celdas" aria-hidden>
          <span className="celda-muestra running" /> trabajando
          <span className="celda-muestra done" /> listo
          <span className="celda-muestra error" /> rechazo
        </div>
      </div>

      {grupos.map(([nivel, especs]) => (
        <div key={nivel} className="nivel-carriles">
          <div className="etiqueta-nivel">
            <span className="mono">Nivel {nivel}</span>
            {especs.length > 1 ? (
              <span className="chip-paralelo">⇉ {especs.length} en paralelo</span>
            ) : (
              <span className="apagado">{nivel === 1 ? "base" : "secuencial"}</span>
            )}
          </div>
          {especs.map((e) => {
            const carril = carriles.get(e.id);
            const terminada = e.estado === "aprobada" || e.estado === "fallida" || e.estado === "bloqueada";
            return (
              <div key={e.id} className={`carril ${carril?.activo ? "vivo" : ""} ${claseEncargo(e.estado)}`}>
                <div className="carril-id">
                  <span className="mono">{e.id}</span>
                  <span className="carril-titulo" title={e.titulo}>
                    {e.titulo}
                  </span>
                </div>
                <div className="carril-etapas">
                  {ETAPAS_ESPEC.map((etapa) => {
                    let estado = carril?.etapas[etapa.agente] ?? "pending";
                    if (etapa.agente === "diagnosticador" && !carril?.vioDiagnostico) {
                      return <span key={etapa.agente} className="celda omitida" aria-hidden />;
                    }
                    // Una aprobada tiene todas sus etapas hechas, aunque la pestaña
                    // se haya abierto después de los eventos.
                    if (e.estado === "aprobada" && estado === "pending") estado = "done";
                    return (
                      <span
                        key={etapa.agente}
                        className={`celda ${estado}`}
                        title={`${etapa.etiqueta}: ${estado}`}
                      >
                        {etapa.etiqueta}
                      </span>
                    );
                  })}
                </div>
                <span className={`pastilla-encargo ${claseEncargo(e.estado)}`}>
                  {terminada || e.estado !== "pendiente" ? ETIQUETA_ESPEC[e.estado] : "En cola"}
                  {e.intentos > 1 ? ` · ${e.intentos} intentos` : ""}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </section>
  );
}
