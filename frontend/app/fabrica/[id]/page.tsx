"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import LogStream from "@/components/LogStream";
import CarrilesParalelos from "@/components/fabrica/CarrilesParalelos";
import LineaDeTiempo, { resumenParalelismo } from "@/components/fabrica/LineaDeTiempo";
import { AlertTriangle, CheckCircle2, Hand, Loader2, Play, Square, XCircle } from "lucide-react";
import {
  bitacoraEncargo,
  configFabrica,
  decidirEspecificacion,
  detenerEncargo,
  finalizarEncargo,
  metricasEncargo,
  obtenerEncargo,
  reanudarEncargo,
  responderPregunta,
} from "@/lib/api";
import {
  ETAPAS_FABRICA,
  ETIQUETA_ENCARGO,
  ETIQUETA_ESPEC,
  type Situacion,
  claseEncargo,
  derivarCarriles,
  situacionEncargo,
  usd,
} from "@/lib/fabrica";
import type {
  ConfigFabrica,
  Encargo,
  Integridad,
  MetricasEncargo,
  Pregunta,
  RegistroBitacora,
} from "@/lib/types";
import { useEventos } from "@/lib/ws";

function TarjetaPregunta({
  pregunta,
  onResponder,
}: {
  pregunta: Pregunta;
  onResponder: (respuesta: string) => Promise<void>;
}) {
  const [libre, setLibre] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(respuesta: string) {
    setEnviando(true);
    try {
      await onResponder(respuesta);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <article className="tarjeta-decision">
      <span className="etiqueta-subseccion">
        {pregunta.origen === "diagnosticador" ? "El Diagnosticador pregunta" : "El Especificador pregunta"}
      </span>
      <p>{pregunta.texto}</p>
      {pregunta.propuesta && (
        <div className="propuesta-modal">
          <span className="etiqueta-subseccion">Propuesta del Diagnosticador</span>
          <p>{pregunta.propuesta}</p>
        </div>
      )}
      <div className="fila-pastillas">
        {pregunta.opciones.map((o) => (
          <button key={o} type="button" disabled={enviando} onClick={() => enviar(o)}>
            {o}
          </button>
        ))}
      </div>
      <form
        className="fila-alta"
        onSubmit={(e) => {
          e.preventDefault();
          if (libre.trim()) void enviar(libre.trim());
        }}
      >
        <input
          value={libre}
          onChange={(e) => setLibre(e.target.value)}
          placeholder="…o escribí otra respuesta"
          aria-label="Respuesta libre"
        />
        <button type="submit" disabled={enviando || !libre.trim()}>
          Responder
        </button>
      </form>
    </article>
  );
}

const ICONO_TONO = { ok: CheckCircle2, espera: Hand, mal: XCircle, neutro: Loader2 } as const;

/**
 * Qué está pasando y qué puede hacer la persona, arriba de todo. Cerrar pide
 * una confirmación en el mismo botón (sin diálogos del navegador): deja lo
 * pendiente como sin terminar y no se deshace.
 */
function BannerSituacion({
  situacion,
  hayDecisiones,
  onDetener,
  onReanudar,
  onCerrar,
}: {
  situacion: Situacion;
  hayDecisiones: boolean;
  onDetener: () => Promise<void>;
  onReanudar: () => Promise<void>;
  onCerrar: () => Promise<void>;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const Icono = ICONO_TONO[situacion.tono];

  async function correr(fn: () => Promise<void>) {
    setOcupado(true);
    try {
      await fn();
    } finally {
      setOcupado(false);
      setConfirmando(false);
    }
  }

  return (
    <section className={`banner-situacion ${situacion.tono}`} aria-live="polite">
      <Icono size={22} aria-hidden className={situacion.tono === "neutro" ? "girando" : ""} />
      <div className="texto-situacion">
        <strong>{situacion.titulo}</strong>
        <span>{situacion.detalle}</span>
      </div>
      <div className="acciones-situacion">
        {hayDecisiones && (
          <a className="boton-enlace" href="#decisiones">
            Ir a las decisiones
          </a>
        )}
        {situacion.puedeReanudar && (
          <button type="button" className="primario" disabled={ocupado} onClick={() => correr(onReanudar)}>
            <Play size={14} aria-hidden /> Reanudar
          </button>
        )}
        {situacion.puedeDetener && (
          <button type="button" disabled={ocupado} onClick={() => correr(onDetener)}>
            <Square size={14} aria-hidden /> Detener
          </button>
        )}
        {situacion.puedeCerrar &&
          (confirmando ? (
            <>
              <button type="button" className="peligro" disabled={ocupado} onClick={() => correr(onCerrar)}>
                <AlertTriangle size={14} aria-hidden /> Sí, cerrar con lo aprobado
              </button>
              <button type="button" onClick={() => setConfirmando(false)}>
                Cancelar
              </button>
            </>
          ) : (
            <button type="button" disabled={ocupado} onClick={() => setConfirmando(true)}>
              Cerrar con lo aprobado
            </button>
          ))}
      </div>
    </section>
  );
}

export default function PaginaEncargo({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { eventos } = useEventos(600);
  const propios = useMemo(() => eventos.filter((e) => e.run_id === id), [eventos, id]);

  const [encargo, setEncargo] = useState<Encargo | null>(null);
  const [metricas, setMetricas] = useState<MetricasEncargo | null>(null);
  const [bitacora, setBitacora] = useState<{ integridad: Integridad; registros: RegistroBitacora[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigFabrica | null>(null);

  useEffect(() => {
    configFabrica().then(setConfig).catch(() => {});
  }, []);

  const cargar = useCallback(() => {
    obtenerEncargo(id)
      .then(setEncargo)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
    metricasEncargo(id).then(setMetricas).catch(() => {});
    bitacoraEncargo(id).then(setBitacora).catch(() => {});
  }, [id]);

  // Cada evento del encargo es una señal de que algo cambió en el backend.
  useEffect(() => {
    cargar();
  }, [cargar, propios.length]);

  const estadoEtapa = useMemo(() => {
    const mapa = new Map<string, { status: string; msg: string }>();
    for (const e of propios) mapa.set(e.agent, { status: e.status, msg: e.msg });
    return mapa;
  }, [propios]);

  // Cuántas instancias de cada agente están trabajando a la vez ahora mismo.
  const instancias = useMemo(() => {
    const conteo = new Map<string, number>();
    const ids = encargo?.especificaciones.map((e) => e.id) ?? [];
    for (const carril of derivarCarriles(propios, ids, encargo?.corriendo ?? false).values()) {
      for (const [agente, estado] of Object.entries(carril.etapas)) {
        if (estado === "running") conteo.set(agente, (conteo.get(agente) ?? 0) + 1);
      }
    }
    return conteo;
  }, [propios, encargo]);

  const paralelo = useMemo(
    () => (metricas && metricas.etapas.length ? resumenParalelismo(metricas.etapas) : null),
    [metricas],
  );

  async function accion(fn: () => Promise<Encargo>) {
    setError(null);
    try {
      setEncargo(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "La acción falló");
    }
  }

  if (!encargo) {
    return (
      <main className="contenido">
        {error ? <p className="error">{error}</p> : <p className="apagado">Cargando…</p>}
      </main>
    );
  }

  const abiertas = encargo.preguntas.filter((p) => p.respuesta === null);

  const aprobadas = encargo.especificaciones.filter((e) => e.estado === "aprobada").length;
  const total = encargo.especificaciones.length;
  const sinResolver = encargo.especificaciones.filter(
    (e) => e.estado === "fallida" || e.estado === "bloqueada",
  ).length;
  const esperandoAprobacion = encargo.especificaciones.filter(
    (e) => e.estado === "esperando_aprobacion",
  ).length;
  const situacion = situacionEncargo(encargo);
  const ahorro =
    paralelo && paralelo.secuencial > paralelo.real ? 1 - paralelo.real / paralelo.secuencial : 0;

  return (
    <>
      <header className="cabecera">
        <Link href="/fabrica" className="volver-proyectos">
          ← Fábrica
        </Link>
        <h1>
          Encargo {encargo.id}
          {encargo.version > 1 && <span className="etiqueta-version">v{encargo.version}</span>}
        </h1>
        <span className={`pastilla-encargo ${claseEncargo(encargo.estado)}`}>
          {ETIQUETA_ENCARGO[encargo.estado]}
          {encargo.corriendo ? " · corriendo" : ""}
        </span>
      </header>

      <main className="contenido">
        <section className={`portada-encargo ${encargo.corriendo ? "en-marcha" : ""}`}>
          <p className="pedido-portada">{encargo.pedido}</p>
          <p className="linaje-portada">
            {encargo.padre_id ? (
              <>
                Versión {encargo.version}, parte de los archivos de{" "}
                <Link href={`/fabrica/${encargo.padre_id}`}>{encargo.padre_id}</Link> ·{" "}
              </>
            ) : (
              <>Versión 1 · </>
            )}
            {encargo.archivado_en && <>archivada · </>}
            <Link href="/fabrica/ejecuciones">Crear una nueva versión desde Ejecuciones</Link>
          </p>
          <div className="kpis-portada">
            <div>
              <span>Especificaciones</span>
              <strong className="mono">
                {aprobadas}/{encargo.especificaciones.length}
              </strong>
              <small>aprobadas</small>
            </div>
            <div>
              <span>Concurrencia máxima</span>
              <strong className="mono">{paralelo ? `×${paralelo.maxima}` : "—"}</strong>
              <small>tope configurado ×{config?.paralelismo ?? "…"}</small>
            </div>
            <div>
              <span>Tiempo real</span>
              <strong className="mono">{paralelo ? `${paralelo.real.toFixed(1)} s` : "—"}</strong>
              <small>
                {paralelo ? `${paralelo.secuencial.toFixed(1)} s si fuera en fila` : "sin etapas aún"}
              </small>
            </div>
            <div>
              <span>Ahorro por paralelismo</span>
              <strong className="mono">{ahorro > 0 ? `${Math.round(ahorro * 100)}%` : "—"}</strong>
              <small>del tiempo secuencial</small>
            </div>
            <div>
              <span>Costo</span>
              <strong className="mono">{usd(encargo.costo_usd)}</strong>
              <small>
                {config?.orquestador === "prefect" && config.prefect_ui_url ? (
                  <a href={config.prefect_ui_url} target="_blank" rel="noreferrer">
                    ver en Prefect ↗
                  </a>
                ) : (
                  "orquestado con asyncio"
                )}
              </small>
            </div>
          </div>
          {total > 0 && (
            <div
              className="barra-progreso"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={aprobadas}
              aria-label="Especificaciones aprobadas"
            >
              <i className="ok" style={{ width: `${(aprobadas / total) * 100}%` }} />
              <i className="mal" style={{ width: `${(sinResolver / total) * 100}%` }} />
            </div>
          )}
        </section>

        <BannerSituacion
          situacion={situacion}
          hayDecisiones={abiertas.length > 0 || esperandoAprobacion > 0}
          onDetener={() => accion(() => detenerEncargo(id))}
          onReanudar={() => accion(() => reanudarEncargo(id))}
          onCerrar={() => accion(() => finalizarEncargo(id))}
        />
        {error && <p className="error">{error}</p>}

        {abiertas.length > 0 && (
          <section id="decisiones">
            <h2 className="titulo-seccion">Decisiones pendientes</h2>
            {abiertas.map((p) => (
              <TarjetaPregunta
                key={p.id}
                pregunta={p}
                onResponder={(r) => accion(() => responderPregunta(id, p.id, r))}
              />
            ))}
          </section>
        )}

        <ol className="flujo-agentes" aria-label="Agentes del pipeline">
          {ETAPAS_FABRICA.map((etapa) => {
            const estado = estadoEtapa.get(etapa.agente);
            const n = instancias.get(etapa.agente) ?? 0;
            let clase = n > 0 ? "running" : (estado?.status ?? "pending");
            // El servidor es la verdad: sin tarea en curso, nada está trabajando.
            if (clase === "running" && !encargo.corriendo)
              clase = encargo.estado === "terminado" ? "done" : "pending";
            return (
              <li key={etapa.agente} className={`nodo-agente ${clase}`}>
                <span className="punto" />
                <strong>{etapa.etiqueta}</strong>
                {n > 1 && <span className="chip-instancias">×{n} en paralelo</span>}
                <span className="msg-etapa">{estado?.msg ?? "—"}</span>
              </li>
            );
          })}
        </ol>

        <CarrilesParalelos
          especificaciones={encargo.especificaciones}
          eventos={propios}
          paralelismo={config?.paralelismo ?? 1}
          vivo={encargo.corriendo}
        />

        <h2 className="titulo-seccion">Detalle de las especificaciones</h2>
        {encargo.especificaciones.length === 0 && (
          <p className="apagado">
            {encargo.estado === "esperando_humano"
              ? "Se especifica después de responder las preguntas."
              : "Todavía no hay especificaciones."}
          </p>
        )}
        <div className="rejilla-tareas">
          {encargo.especificaciones.map((e) => (
            <article key={e.id} className="tarjeta-tarea">
              <div className="cabecera-tarea">
                <span className={`pastilla-encargo ${claseEncargo(e.estado)}`}>{e.id}</span>
                <h3>{e.titulo}</h3>
              </div>
              <div className="cuerpo-tarea">
                {e.estrategia === "reescritura" && (
                  <span className="chip-estrategia">
                    {e.estado === "en_curso" ? "reescribiendo desde cero" : "se reescribió desde cero"}
                  </span>
                )}
                <span className="apagado">
                  {ETIQUETA_ESPEC[e.estado]} · {e.rondas ?? e.intentos} intento(s)
                  {config?.max_rondas ? ` de ${config.max_rondas} como máximo` : ""}
                  {e.depende_de.length > 0 && ` · depende de ${e.depende_de.join(", ")}`}
                  {e.requiere_aprobacion && " · requiere aprobación"}
                  {e.e2e && " · e2e"}
                </span>
                <ul className="lista-archivos mono">
                  {e.archivos.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
                {e.motivo && <p className="error">{e.motivo}</p>}
                {e.estado === "esperando_aprobacion" && (
                  <div className="fila-alta">
                    <button type="button" onClick={() => accion(() => decidirEspecificacion(id, e.id, true))}>
                      Aprobar
                    </button>
                    <button
                      type="button"
                     
                      onClick={() => accion(() => decidirEspecificacion(id, e.id, false))}
                    >
                      Rechazar
                    </button>
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>

        <details className="seccion-plegable">
          <summary>
            <span>Detalles técnicos</span>
            <small className="apagado">línea de tiempo, costos por etapa, bitácora sellada y eventos en vivo</small>
          </summary>
        <h2 className="titulo-seccion">Línea de tiempo</h2>
        <p className="apagado">
          Cada barra es una etapa con su duración real. Barras en la misma franja vertical, en filas
          distintas: especificaciones construyéndose a la vez.
        </p>
        {metricas && <LineaDeTiempo metricas={metricas.etapas} />}

        <h2 className="titulo-seccion">Costo y tiempo por etapa</h2>
        {metricas && (
          <>
            <p className="apagado">
              Total: {usd(metricas.costo_total_usd)}
              {!metricas.costo_completo && " (hay etapas sin tarifa conocida)"} ·{" "}
              {metricas.duracion_total_s.toFixed(1)} s · {metricas.tokens_total} tokens
            </p>
            <table className="tabla">
              <thead>
                <tr>
                  <th>Etapa</th>
                  <th>Espec.</th>
                  <th>Intento</th>
                  <th>Resultado</th>
                  <th>Modelo</th>
                  <th>Tokens</th>
                  <th>Costo</th>
                  <th>Duración</th>
                </tr>
              </thead>
              <tbody>
                {metricas.etapas.map((m, i) => (
                  <tr key={`${m.ts}-${i}`}>
                    <td>{m.etapa}</td>
                    <td className="mono">{m.espec_id ?? "—"}</td>
                    <td className="mono">{m.intento}</td>
                    <td>{m.resultado}</td>
                    <td className="mono">{m.modelo || "—"}</td>
                    <td className="mono">{m.tokens_entrada + m.tokens_salida}</td>
                    <td className="mono">{usd(m.costo_usd)}</td>
                    <td className="mono">{m.duracion_s.toFixed(2)} s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <h2 className="titulo-seccion">Bitácora</h2>
        {bitacora && (
          <>
            <p className={bitacora.integridad.integra ? "apagado" : "error"}>
              {bitacora.integridad.integra
                ? `Cadena íntegra: ${bitacora.integridad.registros} registros sellados`
                : `Cadena rota desde el registro ${bitacora.integridad.primer_registro_roto}`}
            </p>
            <ol className="bitacora">
              {bitacora.registros.map((r) => (
                <li key={r.secuencia}>
                  <span className="mono apagado">#{r.secuencia}</span> <strong>{r.agente}</strong> ·{" "}
                  {r.accion} <span className="mono apagado hash">{r.hash.slice(0, 12)}</span>
                  <details>
                    <summary>evidencia</summary>
                    <pre className="mono">{JSON.stringify(r.evidencia, null, 2)}</pre>
                  </details>
                </li>
              ))}
            </ol>
          </>
        )}

        <h2 className="titulo-seccion">Eventos en vivo</h2>
        <LogStream eventos={propios} />
        </details>
      </main>
    </>
  );
}
