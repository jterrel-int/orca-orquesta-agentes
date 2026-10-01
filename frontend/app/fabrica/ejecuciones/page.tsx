"use client";

import { FolderOpen, GitBranchPlus, Play, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import ExploradorArchivos, { tamano } from "@/components/fabrica/ExploradorArchivos";
import { crearEncargo, listarEjecuciones, reanudarEncargo } from "@/lib/api";
import { ETIQUETA_ENCARGO, claseEncargo, usd } from "@/lib/fabrica";
import type { Ejecucion } from "@/lib/types";

function fecha(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" });
}

/** Todas las versiones de un mismo producto, de la más vieja a la más nueva. */
interface Producto {
  raiz: string;
  versiones: Ejecucion[];
  ultima: Ejecucion;
}

function agrupar(ejecuciones: Ejecucion[]): Producto[] {
  const grupos = new Map<string, Ejecucion[]>();
  for (const e of ejecuciones) {
    const raiz = e.raiz_id ?? e.id;
    grupos.set(raiz, [...(grupos.get(raiz) ?? []), e]);
  }
  return [...grupos.entries()]
    .map(([raiz, versiones]) => {
      versiones.sort((a, b) => a.version - b.version || (a.creado_en ?? "").localeCompare(b.creado_en ?? ""));
      return { raiz, versiones, ultima: versiones[versiones.length - 1] };
    })
    .sort((a, b) => (b.ultima.creado_en ?? "").localeCompare(a.ultima.creado_en ?? ""));
}

function FormularioIteracion({
  base,
  siguiente,
  onCancelar,
}: {
  base: Ejecucion;
  siguiente: number;
  onCancelar: () => void;
}) {
  const router = useRouter();
  const [pedido, setPedido] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    if (pedido.trim().length < 3) return;
    setEnviando(true);
    setError(null);
    try {
      await crearEncargo(pedido.trim(), base.id);
      // A la oficina: ahí se ve a los agentes trabajar sobre la versión cargada.
      router.push("/fabrica");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear la versión");
      setEnviando(false);
    }
  }

  return (
    <form className="formulario-iteracion" onSubmit={crear}>
      <label className="etiqueta-campo" htmlFor={`iterar-${base.id}`}>
        ¿Qué cambiamos o agregamos en la <strong>v{siguiente}</strong>? Parte de los archivos de la v
        {base.version} ({base.id}).
      </label>
      <textarea
        id={`iterar-${base.id}`}
        rows={3}
        value={pedido}
        onChange={(e) => setPedido(e.target.value)}
        placeholder="Ej.: Agregar un botón para exportar las tareas a CSV. Mostrar la fecha de creación de cada tarea."
        autoFocus
      />
      <div className="fila-alta">
        <button type="submit" className="primario" disabled={enviando || pedido.trim().length < 3}>
          {enviando ? "Creando…" : `Crear v${siguiente} y cargarla en la línea`}
        </button>
        <button type="button" onClick={onCancelar} disabled={enviando}>
          Cancelar
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

export default function PaginaEjecuciones() {
  const router = useRouter();
  const [ejecuciones, setEjecuciones] = useState<Ejecucion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [archivosDe, setArchivosDe] = useState<string | null>(null);
  const [iterarDesde, setIterarDesde] = useState<string | null>(null);

  const cargar = useCallback(() => {
    listarEjecuciones()
      .then(setEjecuciones)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
  }, []);

  useEffect(() => {
    cargar();
    const intervalo = setInterval(cargar, 5000);
    return () => clearInterval(intervalo);
  }, [cargar]);

  const productos = useMemo(() => agrupar(ejecuciones ?? []), [ejecuciones]);

  /** Reanuda (si quedó a medias) o devuelve a la línea (si solo estaba archivado). */
  async function cargarEnLinea(id: string) {
    try {
      await reanudarEncargo(id);
      router.push("/fabrica");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo reanudar");
    }
  }

  return (
    <>
      <header className="cabecera">
        <Link href="/fabrica" className="volver-proyectos">
          ← Fábrica
        </Link>
        <h1>Ejecuciones</h1>
        <span className="sub">
          Todo lo que construyó la fábrica, desde sus carpetas en fabrica_espacios/. Carga una versión y
          sigue iterando: cada iteración es una versión nueva.
        </span>
      </header>

      <main className="contenido">
        {error && <p className="error">{error}</p>}
        {ejecuciones === null && !error && <p className="apagado">Cargando…</p>}
        {ejecuciones?.length === 0 && (
          <p className="apagado">
            Todavía no hay ejecuciones. <Link href="/fabrica">Encarga algo</Link> y aparecerá acá.
          </p>
        )}

        <div className="productos">
          {productos.map((producto) => {
            const v1 = producto.versiones[0];
            const siguiente = Math.max(...producto.versiones.map((v) => v.version)) + 1;
            const iterable = producto.ultima.en_base;
            return (
              <section key={producto.raiz} className="producto">
                <header className="cabecera-producto">
                  <div>
                    <span className="etiqueta-subseccion">
                      {producto.versiones.length === 1 ? "1 versión" : `${producto.versiones.length} versiones`}
                    </span>
                    <h2>{v1.pedido ?? `Carpeta ${v1.id} (sin registro en la base)`}</h2>
                  </div>
                  {iterable && (
                    <button
                      type="button"
                      className="primario"
                      onClick={() => setIterarDesde(producto.ultima.id)}
                    >
                      <GitBranchPlus size={16} aria-hidden /> Continuar iterando (v{producto.ultima.version} → v
                      {siguiente})
                    </button>
                  )}
                </header>

                <ol className="versiones">
                  {producto.versiones.map((v) => (
                    <li key={v.id} className={`version ${v.id === producto.ultima.id ? "ultima" : ""}`}>
                      <div className="fila-version">
                        <span className="numero-version">v{v.version}</span>
                        <div className="datos-version">
                          <div className="linea-estado">
                            {v.estado ? (
                              <span className={`pastilla-encargo ${claseEncargo(v.estado)}`}>
                                {ETIQUETA_ENCARGO[v.estado]}
                                {v.corriendo ? " · corriendo" : ""}
                              </span>
                            ) : (
                              <span className="pastilla-encargo neutro">Sin registro</span>
                            )}
                            {v.archivado_en && <span className="pastilla-encargo neutro">Archivada</span>}
                            <span className="mono apagado">{v.id}</span>
                          </div>
                          <p className="pedido-version">
                            {v.version > 1 && <span className="apagado">Cambio: </span>}
                            {v.pedido ?? "—"}
                          </p>
                          <span className="apagado metadatos-version">
                            {fecha(v.creado_en)} · {v.aprobadas}/{v.especificaciones} especificaciones ·{" "}
                            {v.carpeta ? `${v.archivos} archivos (${tamano(v.bytes)})` : "sin carpeta"} ·{" "}
                            {usd(v.costo_usd)}
                          </span>
                        </div>
                        <div className="acciones-version">
                          {v.en_base && <Link href={`/fabrica/${v.id}`}>Ver</Link>}
                          {v.carpeta && (
                            <button
                              type="button"
                              onClick={() => setArchivosDe(archivosDe === v.id ? null : v.id)}
                              aria-expanded={archivosDe === v.id}
                            >
                              <FolderOpen size={15} aria-hidden /> Archivos
                            </button>
                          )}
                          {v.en_base &&
                            !v.corriendo &&
                            (v.archivado_en || v.estado === "interrumpido" || v.estado === "fallido") && (
                              <button type="button" onClick={() => cargarEnLinea(v.id)}>
                                <Play size={15} aria-hidden />{" "}
                                {v.estado === "interrumpido" || v.estado === "fallido" ? "Reanudar" : "Cargar en la línea"}
                              </button>
                            )}
                          {v.en_base && (
                            <button type="button" onClick={() => setIterarDesde(v.id)}>
                              <RotateCcw size={15} aria-hidden /> Nueva versión desde aquí
                            </button>
                          )}
                        </div>
                      </div>
                      {iterarDesde === v.id && (
                        <FormularioIteracion base={v} siguiente={siguiente} onCancelar={() => setIterarDesde(null)} />
                      )}
                      {archivosDe === v.id && <ExploradorArchivos ejecucionId={v.id} />}
                    </li>
                  ))}
                </ol>
              </section>
            );
          })}
        </div>
      </main>
    </>
  );
}
