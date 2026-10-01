"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { MetricaEtapa } from "@/lib/types";

/**
 * Gantt con los tiempos reales de cada etapa (fabrica_metricas: `ts` es el
 * fin, `duracion_s` la duración). Si dos filas tienen barras en la misma
 * franja vertical, esas especificaciones se construyeron a la vez — es la
 * evidencia del paralelismo, no una animación.
 */

// Paleta categórica validada (slots 1–4 en orden fijo; ver skill dataviz).
// Aqua y amarillo quedan bajo 3:1 contra el blanco: por eso la leyenda lleva
// texto, cada barra tiene tooltip y la tabla de métricas sigue en la página.
const ETAPAS = [
  { etapa: "implementacion", etiqueta: "Implementación", color: "var(--etapa-1)" },
  { etapa: "revision", etiqueta: "Revisión", color: "var(--etapa-2)" },
  { etapa: "verificacion", etiqueta: "Verificación", color: "var(--etapa-3)" },
  { etapa: "diagnostico", etiqueta: "Diagnóstico", color: "var(--etapa-4)" },
] as const;
const COLOR_ENCARGO = "var(--etapa-encargo)";

const ALTO_FILA = 30;
const ALTO_BARRA = 14;
const MARGEN_IZQ = 76;
const MARGEN_DER = 16;
const ALTO_EJE = 26;
const PASOS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];

interface Barra {
  fila: string;
  etapa: string;
  inicio: number;
  fin: number;
  m: MetricaEtapa;
}

function formatoSeg(s: number): string {
  if (s >= 60) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  return s < 1 ? `${s.toFixed(2)} s` : `${s.toFixed(1)} s`;
}

/** Mismos decimales en todo el eje, según el tamaño del paso. */
function formatoEje(s: number, paso: number): string {
  if (paso >= 60) return `${Math.round(s / 60)} min`;
  const decimales = paso < 0.1 ? 2 : paso < 1 ? 1 : 0;
  return `${s.toFixed(decimales)} s`;
}

export function resumenParalelismo(metricas: MetricaEtapa[]) {
  const barras = metricas
    .map((m) => {
      const fin = Date.parse(m.ts) / 1000;
      return { m, inicio: fin - m.duracion_s, fin };
    })
    .filter((b) => Number.isFinite(b.fin));
  const deEspec = barras.filter((b) => b.m.espec_id !== null);
  // Barrido: +1 al empezar, −1 al terminar (los fines primero ante un empate).
  const marcas = deEspec.flatMap((b) => [
    { t: b.inicio, d: 1 },
    { t: b.fin, d: -1 },
  ]);
  marcas.sort((a, b) => a.t - b.t || a.d - b.d);
  let actual = 0;
  let maxima = 0;
  for (const x of marcas) {
    actual += x.d;
    maxima = Math.max(maxima, actual);
  }
  const t0 = Math.min(...barras.map((b) => b.inicio));
  const t1 = Math.max(...barras.map((b) => b.fin));
  const real = barras.length ? t1 - t0 : 0;
  const secuencial = barras.reduce((s, b) => s + b.m.duracion_s, 0);
  return { maxima, real, secuencial, t0, t1 };
}

export default function LineaDeTiempo({ metricas }: { metricas: MetricaEtapa[] }) {
  const contenedor = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(720);
  const [foco, setFoco] = useState<{ barra: Barra; x: number; y: number } | null>(null);

  useEffect(() => {
    const el = contenedor.current;
    if (!el) return;
    const obs = new ResizeObserver(([entrada]) => setAncho(Math.max(320, entrada.contentRect.width)));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const { barras, filas, t0, span, pasos } = useMemo(() => {
    const barras: Barra[] = metricas
      .map((m) => {
        const fin = Date.parse(m.ts) / 1000;
        return { fila: m.espec_id ?? "Encargo", etapa: m.etapa, inicio: fin - m.duracion_s, fin, m };
      })
      .filter((b) => Number.isFinite(b.fin));
    const ids = [...new Set(barras.map((b) => b.fila))]
      .filter((f) => f !== "Encargo")
      .sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)) || a.localeCompare(b));
    const filas = barras.some((b) => b.fila === "Encargo") ? ["Encargo", ...ids] : ids;
    const t0 = Math.min(...barras.map((b) => b.inicio));
    const span = Math.max(0.05, Math.max(...barras.map((b) => b.fin)) - t0);
    const paso = PASOS.find((p) => span / p <= 7) ?? 3600;
    const pasos = Array.from({ length: Math.floor(span / paso) + 1 }, (_, i) => i * paso);
    return { barras, filas, t0, span, pasos };
  }, [metricas]);

  if (barras.length === 0) {
    return <p className="apagado">La línea de tiempo aparece cuando termina la primera etapa.</p>;
  }

  const anchoUtil = ancho - MARGEN_IZQ - MARGEN_DER;
  const x = (t: number) => MARGEN_IZQ + ((t - t0) / span) * anchoUtil;
  const alto = filas.length * ALTO_FILA + ALTO_EJE;
  const colorDe = (etapa: string) => ETAPAS.find((e) => e.etapa === etapa)?.color ?? COLOR_ENCARGO;

  return (
    <div className="linea-tiempo" ref={contenedor}>
      <div className="leyenda-tiempo">
        {ETAPAS.map((e) => (
          <span key={e.etapa}>
            <i style={{ background: e.color }} /> {e.etiqueta}
          </span>
        ))}
        <span>
          <i style={{ background: COLOR_ENCARGO }} /> Especificación / despliegue
        </span>
      </div>
      <div className="lienzo-tiempo">
      <svg
        width={ancho}
        height={alto}
        role="img"
        aria-label={`Línea de tiempo de ${filas.length} filas y ${barras.length} etapas`}
        onMouseLeave={() => setFoco(null)}
      >
        {pasos.map((p) => (
          <g key={p}>
            <line x1={x(t0 + p)} x2={x(t0 + p)} y1={0} y2={alto - ALTO_EJE} className="grilla-tiempo" />
            <text x={x(t0 + p)} y={alto - 8} textAnchor="middle" className="eje-tiempo">
              {formatoEje(p, pasos[1] ?? 1)}
            </text>
          </g>
        ))}
        {filas.map((fila, i) => (
          <g key={fila} transform={`translate(0, ${i * ALTO_FILA})`}>
            <text x={0} y={ALTO_FILA / 2 + 4} className="fila-tiempo">
              {fila}
            </text>
          </g>
        ))}
        {barras.map((b, i) => {
          const fila = filas.indexOf(b.fila);
          // 1px de aire a cada lado: dos etapas contiguas quedan separadas por 2px.
          const bx = x(b.inicio) + 1;
          const bw = Math.max(3, x(b.fin) - x(b.inicio) - 2);
          const y = fila * ALTO_FILA + (ALTO_FILA - ALTO_BARRA) / 2;
          const activa = foco?.barra === b;
          return (
            <g key={i}>
              <rect
                x={bx}
                y={y}
                width={bw}
                height={ALTO_BARRA}
                rx={4}
                fill={colorDe(b.etapa)}
                opacity={foco && !activa ? 0.45 : 1}
                className={b.m.resultado === "rechazo" || b.m.resultado === "error" ? "barra-rechazo" : ""}
              />
              {/* Área de toque más grande que la barra. */}
              <rect
                x={bx - 3}
                y={fila * ALTO_FILA}
                width={bw + 6}
                height={ALTO_FILA}
                fill="transparent"
                onMouseEnter={() => setFoco({ barra: b, x: bx + bw / 2, y })}
              />
            </g>
          );
        })}
      </svg>
      {foco && (
        <div
          className="tooltip-tiempo"
          style={{ left: Math.min(Math.max(foco.x, 110), ancho - 110), top: foco.y }}
          role="status"
        >
          <strong>
            {foco.barra.fila} · {ETAPAS.find((e) => e.etapa === foco.barra.etapa)?.etiqueta ?? foco.barra.etapa}
          </strong>
          <span>
            {formatoSeg(foco.barra.inicio - t0)} → {formatoSeg(foco.barra.fin - t0)} ·{" "}
            {formatoSeg(foco.barra.m.duracion_s)}
          </span>
          <span>
            {foco.barra.m.resultado} · intento {foco.barra.m.intento}
            {foco.barra.m.modelo ? ` · ${foco.barra.m.modelo}` : ""}
          </span>
        </div>
      )}
      </div>
    </div>
  );
}
