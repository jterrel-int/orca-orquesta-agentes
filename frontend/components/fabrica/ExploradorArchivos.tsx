"use client";

import { FileCode2, FileText, Folder } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { archivosEjecucion, leerArchivoEjecucion } from "@/lib/api";
import type { ArchivoEjecucion } from "@/lib/types";

export function tamano(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Los archivos de una ejecución, de solo lectura: lista por carpeta y visor. */
export default function ExploradorArchivos({ ejecucionId }: { ejecucionId: string }) {
  const [archivos, setArchivos] = useState<ArchivoEjecucion[] | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [contenido, setContenido] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    archivosEjecucion(ejecucionId)
      .then((lista) => {
        setArchivos(lista);
        // Abre de entrada el primer archivo de código, que es lo que se suele buscar.
        const primero = lista.find((a) => a.ruta.startsWith("src/") && !a.ruta.endsWith("__init__.py"));
        if (primero) setAbierto(primero.ruta);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "No se pudieron listar"));
  }, [ejecucionId]);

  useEffect(() => {
    if (!abierto) return;
    setContenido("");
    leerArchivoEjecucion(ejecucionId, abierto)
      .then((r) => setContenido(r.contenido))
      .catch((e: unknown) => setContenido(e instanceof Error ? `(${e.message})` : "(no se pudo leer)"));
  }, [ejecucionId, abierto]);

  const porCarpeta = useMemo(() => {
    const grupos = new Map<string, ArchivoEjecucion[]>();
    for (const a of archivos ?? []) {
      const carpeta = a.ruta.includes("/") ? a.ruta.slice(0, a.ruta.lastIndexOf("/")) : ".";
      grupos.set(carpeta, [...(grupos.get(carpeta) ?? []), a]);
    }
    return [...grupos.entries()];
  }, [archivos]);

  if (error) return <p className="error">{error}</p>;
  if (!archivos) return <p className="apagado">Cargando archivos…</p>;
  if (archivos.length === 0) return <p className="apagado">Esta ejecución no tiene archivos.</p>;

  return (
    <div className="explorador">
      <nav className="arbol-archivos" aria-label="Archivos de la ejecución">
        {porCarpeta.map(([carpeta, lista]) => (
          <div key={carpeta}>
            <span className="carpeta">
              <Folder size={14} aria-hidden /> {carpeta}
            </span>
            <ul>
              {lista.map((a) => {
                const Icono = a.ruta.endsWith(".py") || a.ruta.endsWith(".ts") || a.ruta.endsWith(".tsx")
                  ? FileCode2
                  : FileText;
                return (
                  <li key={a.ruta}>
                    <button
                      type="button"
                      className={abierto === a.ruta ? "activo" : ""}
                      onClick={() => setAbierto(a.ruta)}
                    >
                      <Icono size={14} aria-hidden />
                      <span>{a.ruta.slice(a.ruta.lastIndexOf("/") + 1)}</span>
                      <small>{tamano(a.bytes)}</small>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="visor-archivo">
        {abierto ? (
          <>
            <span className="mono ruta-visor">{abierto}</span>
            <pre className="mono">{contenido || "…"}</pre>
          </>
        ) : (
          <p className="apagado">Elige un archivo.</p>
        )}
      </div>
    </div>
  );
}
