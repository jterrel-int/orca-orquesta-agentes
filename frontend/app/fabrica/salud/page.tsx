"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  type EstadoCacheLLM,
  estadoCacheLLM,
  limpiarCacheLLM,
  pluginsFabrica,
  saludFabrica,
} from "@/lib/api";
import { usd } from "@/lib/fabrica";
import type { NivelSalud, SaludFabrica } from "@/lib/types";

const ETIQUETA_NIVEL: Record<NivelSalud, string> = {
  ok: "Estable",
  atencion: "Atención",
  critico: "Crítico",
};

function Signo({ titulo, valor }: { titulo: string; valor: string | number }) {
  return (
    <div className="signo-vital">
      <span className="etiqueta-subseccion">{titulo}</span>
      <strong className="mono">{valor}</strong>
    </div>
  );
}

export default function PaginaSalud() {
  const [salud, setSalud] = useState<SaludFabrica | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cache, setCache] = useState<EstadoCacheLLM | null>(null);
  const [plugins, setPlugins] = useState<{ cargados: string[]; errores: string[] } | null>(null);

  useEffect(() => {
    estadoCacheLLM().then(setCache).catch(() => {});
    pluginsFabrica().then(setPlugins).catch(() => {});
  }, []);

  useEffect(() => {
    const cargar = () =>
      saludFabrica()
        .then(setSalud)
        .catch((e: unknown) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
    cargar();
    const intervalo = setInterval(cargar, 10000);
    return () => clearInterval(intervalo);
  }, []);

  if (!salud) {
    return (
      <main className="contenido">
        {error ? <p className="error">{error}</p> : <p className="apagado">Cargando…</p>}
      </main>
    );
  }

  const s = salud.signos;
  const maxAprobadas = Math.max(1, ...salud.velocidad.map((p) => p.especificaciones_aprobadas));

  return (
    <>
      <header className="cabecera">
        <Link href="/fabrica" className="volver-proyectos">
          ← Fábrica
        </Link>
        <h1>Salud de la fábrica</h1>
        <span className={`pastilla-encargo ${s.estado_general === "ok" ? "ok" : s.estado_general === "critico" ? "mal" : "espera"}`}>
          {ETIQUETA_NIVEL[s.estado_general]}
        </span>
      </header>

      <main className="contenido">
        <p className="apagado">
          Confianza por diseño: en vez de frenar cada encargo con una aprobación, se vigilan los
          signos vitales del sistema y se alerta cuando algo se sale de rango.
        </p>

        {s.alertas.length > 0 && (
          <ul className="alertas-salud">
            {s.alertas.map((a) => (
              <li key={a.signo} className={a.nivel}>
                <strong>{ETIQUETA_NIVEL[a.nivel]}</strong> · {a.mensaje}
              </li>
            ))}
          </ul>
        )}

        <div className="rejilla-signos">
          <Signo titulo="Encargos (24 h)" valor={s.encargos_24h} />
          <Signo titulo="Activos" valor={s.encargos_activos} />
          <Signo titulo="Esperando a una persona" valor={s.esperando_humano} />
          <Signo
            titulo="Aprobadas al primer intento"
            valor={s.tasa_aprobacion_primer_intento == null ? "—" : `${Math.round(s.tasa_aprobacion_primer_intento * 100)}%`}
          />
          <Signo titulo="Especificaciones aprobadas" valor={s.especificaciones_aprobadas} />
          <Signo titulo="Fallidas o bloqueadas" valor={s.especificaciones_fallidas} />
          <Signo titulo="Costo total" valor={usd(s.costo_total_usd)} />
          <Signo titulo="Costo promedio por encargo" valor={usd(s.costo_promedio_encargo_usd)} />
          <Signo titulo="Bitácora" valor={s.bitacora_integra ? "Íntegra" : "Alterada"} />
        </div>

        <h2 className="titulo-seccion">Por etapa</h2>
        <table className="tabla">
          <thead>
            <tr>
              <th>Etapa</th>
              <th>Duración media</th>
              <th>Costo acumulado</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(s.duracion_media_por_etapa_s).map(([etapa, dur]) => (
              <tr key={etapa}>
                <td>{etapa}</td>
                <td className="mono">{dur.toFixed(2)} s</td>
                <td className="mono">{usd(s.costo_por_etapa_usd[etapa] ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {Object.keys(s.rechazos_por_causa).length > 0 && (
          <p className="apagado">
            Rechazos diagnosticados:{" "}
            {Object.entries(s.rechazos_por_causa)
              .map(([causa, n]) => `${causa} ${n}`)
              .join(" · ")}
          </p>
        )}

        <h2 className="titulo-seccion">Caché de respuestas y plugins</h2>
        {cache && (
          <p className="apagado">
            Caché {cache.activa ? "activa" : "apagada (FABRICA_CACHE_LLM=false)"} · {cache.entradas}{" "}
            respuestas guardadas · {cache.aciertos} aciertos · ahorro estimado{" "}
            {usd(cache.ahorro_estimado_usd)} ({cache.tokens_ahorrados} tokens){" "}
            {cache.entradas > 0 && (
              <button
                type="button"
                onClick={() =>
                  limpiarCacheLLM()
                    .then(() => estadoCacheLLM().then(setCache))
                    .catch(() => {})
                }
              >
                Vaciar
              </button>
            )}
          </p>
        )}
        {plugins && (
          <p className="apagado">
            Plugins: {plugins.cargados.length ? plugins.cargados.join(", ") : "ninguno"}
            {plugins.errores.length > 0 && (
              <span className="error"> · con errores: {plugins.errores.join("; ")}</span>
            )}
          </p>
        )}

        <h2 className="titulo-seccion">Velocidad (últimos 14 días)</h2>
        <div className="resultados-encuesta">
          {salud.velocidad.map((p) => (
            <div key={p.dia} className="barra-velocidad">
              <span className="mono apagado">{p.dia.slice(5)}</span>
              <div className="barra-fondo">
                <div
                  className="barra-relleno"
                  style={{ width: `${(p.especificaciones_aprobadas / maxAprobadas) * 100}%` }}
                />
              </div>
              <span className="mono">
                {p.especificaciones_aprobadas} · {usd(p.costo_usd)} · {p.duracion_total_s.toFixed(0)} s
              </span>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
