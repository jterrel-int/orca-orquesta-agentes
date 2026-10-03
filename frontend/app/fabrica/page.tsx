"use client";

import { ListChecks, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import DisenadorSpecs from "@/components/fabrica/DisenadorSpecs";
import OficinaVirtual from "@/components/fabrica/OficinaVirtual";
import PortadaFabrica from "@/components/fabrica/PortadaFabrica";
import { configFabrica, crearEncargo, importarDocumento, listarEncargos } from "@/lib/api";
import { ETIQUETA_ENCARGO, claseEncargo, situacionEncargo } from "@/lib/fabrica";
import type { ConfigFabrica, Encargo } from "@/lib/types";
import { useEventos } from "@/lib/ws";

type Modo = "directo" | "specs";
const CLAVE_MODO = "orquesta.fabrica.modo";

export default function PaginaFabrica() {
  const [modo, setModo] = useState<Modo>("directo");
  const [recienCreado, setRecienCreado] = useState<Encargo | null>(null);

  useEffect(() => {
    try {
      if (localStorage.getItem(CLAVE_MODO) === "specs") setModo("specs");
    } catch {
      // Sin almacenamiento: queda el modo por defecto.
    }
  }, []);

  function cambiarModo(m: Modo) {
    setModo(m);
    try {
      localStorage.setItem(CLAVE_MODO, m);
    } catch {
      // Recordar el modo es una comodidad.
    }
  }

  const [encargos, setEncargos] = useState<Encargo[]>([]);
  const [pedido, setPedido] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigFabrica | null>(null);
  const [importado, setImportado] = useState<string | null>(null);
  const [importando, setImportando] = useState(false);
  const { eventos } = useEventos(800);

  function cargar() {
    listarEncargos()
      .then(setEncargos)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
  }

  useEffect(() => {
    configFabrica().then(setConfig).catch(() => {});
    cargar();
    const intervalo = setInterval(cargar, 4000);
    return () => clearInterval(intervalo);
  }, []);

  async function importar(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    e.target.value = "";
    if (!archivo) return;
    setImportando(true);
    setError(null);
    try {
      const r = await importarDocumento(archivo);
      setPedido(r.pedido);
      setImportado(r.nombre);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo leer el documento");
    } finally {
      setImportando(false);
    }
  }

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!pedido.trim()) return;
    setEnviando(true);
    setError(null);
    try {
      const nuevo = await crearEncargo(pedido.trim());
      setPedido("");
      setImportado(null);
      setEncargos((prev) => [nuevo, ...prev]);
      setRecienCreado(nuevo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear el encargo");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <header className="cabecera">
        <h1>Fábrica</h1>
        <span className="sub">
          Especificador → Implementador → Revisor → Verificador → Despliegue, coordinados por el
          Líder
        </span>
      </header>

      <main className="contenido">
        <PortadaFabrica eventos={eventos} encargos={encargos} config={config} />

        <div className="selector-modo" role="tablist" aria-label="Cómo pedir">
          <button
            type="button"
            role="tab"
            aria-selected={modo === "directo"}
            className={modo === "directo" ? "activo" : ""}
            onClick={() => cambiarModo("directo")}
          >
            <MessageSquareText size={16} aria-hidden />
            <span>
              <strong>Pedido directo</strong>
              <small>Describe todo en un texto y encarga</small>
            </span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={modo === "specs"}
            className={modo === "specs" ? "activo" : ""}
            onClick={() => cambiarModo("specs")}
          >
            <ListChecks size={16} aria-hidden />
            <span>
              <strong>Diseñar por especificaciones</strong>
              <small>Requisito a requisito, con sugerencias y preguntas</small>
            </span>
          </button>
        </div>

        {recienCreado && (
          <p className="aviso-creado">
            Encargo <Link href={`/fabrica/${recienCreado.id}`}>{recienCreado.id}</Link> en marcha.{" "}
            <Link href={`/fabrica/${recienCreado.id}`}>Ver cómo avanza →</Link>
            <button type="button" className="boton-icono" onClick={() => setRecienCreado(null)} aria-label="Cerrar aviso">
              ×
            </button>
          </p>
        )}

        {modo === "specs" ? (
          <DisenadorSpecs
            onEncargar={async (texto) => {
              const nuevo = await crearEncargo(texto);
              setEncargos((prev) => [nuevo, ...prev]);
              setRecienCreado(nuevo);
            }}
          />
        ) : (
        <form className="form-tarea" onSubmit={enviar}>
          <label className="etiqueta-campo" htmlFor="pedido">
            ¿Qué hay que construir?
          </label>
          <textarea
            id="pedido"
            rows={4}
            value={pedido}
            onChange={(e) => {
              setPedido(e.target.value);
              if (!e.target.value) setImportado(null);
            }}
            placeholder="Una oración por funcionalidad; las que no dependan entre sí se construyen en paralelo. Ej.: Registrar productos con nombre y precio. Calcular el total de un carrito con impuestos. Aplicar un cupón de descuento sobre el total."
          />
          <div className="fila-alta">
            <button type="submit" className="primario" disabled={enviando || !pedido.trim()}>
              {enviando ? "Enviando…" : "Encargar"}
            </button>
            <label className="boton-archivo">
              {importando ? "Leyendo…" : "Importar especificación"}
              <input
                type="file"
                accept=".txt,.md,.pdf,.docx"
                onChange={importar}
                disabled={importando}
              />
            </label>
            <Link href="/fabrica/salud">Ver la salud de la fábrica →</Link>
          </div>
          {importado && (
            <p className="apagado">
              Texto importado de <strong>{importado}</strong>. Revísalo y presiona Encargar: cada
              viñeta o párrafo se vuelve una especificación.
            </p>
          )}
          {error && <p className="error">{error}</p>}
        </form>
        )}

        <OficinaVirtual encargos={encargos} eventos={eventos} onCambio={cargar} />

        <div className="titulo-con-enlace">
          <h2 className="titulo-seccion">Encargos en la línea</h2>
          <Link href="/fabrica/ejecuciones">Ver todas las ejecuciones y versiones →</Link>
        </div>
        {encargos.length === 0 && (
          <p className="apagado">
            La línea está vacía. Encarga algo arriba, o carga una ejecución anterior desde{" "}
            <Link href="/fabrica/ejecuciones">Ejecuciones</Link> para seguir iterando.
          </p>
        )}
        <div className="lista-proyectos">
          {encargos.map((e) => (
            <Link
              key={e.id}
              href={`/fabrica/${e.id}`}
              className={`fila-proyecto ${e.corriendo ? "fila-viva" : ""}`}
            >
              <span className={`pastilla-encargo ${claseEncargo(e.estado)}`}>
                {ETIQUETA_ENCARGO[e.estado]}
              </span>
              <span className="info-proyecto">
                <strong>
                  {e.version > 1 && <span className="etiqueta-version">v{e.version}</span>}
                  {e.pedido.length > 90 ? `${e.pedido.slice(0, 90)}…` : e.pedido}
                </strong>
                {!e.corriendo && e.estado !== "terminado" && (
                  <span className={`situacion-fila ${situacionEncargo(e).tono}`}>
                    {situacionEncargo(e).titulo}
                  </span>
                )}
                <span className="descripcion-proyecto mono">
                  {e.id} · {e.especificaciones.length} especificaciones
                  {e.especificaciones.some((s) => s.estado === "en_curso") &&
                    ` · ${e.especificaciones.filter((s) => s.estado === "en_curso").length} en paralelo`}{" "}
                  · USD {e.costo_usd.toFixed(4)}
                </span>
              </span>
              <span className="chevron-proyecto">›</span>
            </Link>
          ))}
        </div>
      </main>
    </>
  );
}
