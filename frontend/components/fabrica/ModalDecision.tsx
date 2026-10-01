"use client";

import { useEffect, useRef, useState } from "react";
import { decidirEspecificacion, responderPregunta } from "@/lib/api";
import type { Decision } from "@/lib/fabrica";
import { PERSONAJES, Retrato } from "./Personaje";

/**
 * Responder a un agente que espera. Usa <dialog> nativo: foco atrapado,
 * Esc para cerrar y fondo inerte sin código propio.
 */
export default function ModalDecision({
  decision,
  total,
  masUrgente,
  onCerrar,
  onRespondida,
  onIrA,
}: {
  decision: Decision | null;
  total: number;
  /** La decisión #1 de la cola, si no es esta. */
  masUrgente: Decision | null;
  onCerrar: () => void;
  /** Se llamó a la API con éxito: recargar y pasar a la siguiente. */
  onRespondida: (clave: string) => void;
  onIrA: (clave: string) => void;
}) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [libre, setLibre] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liberado, setLiberado] = useState<string | null>(null);

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (decision && !d.open) d.showModal();
    if (!decision && d.open) d.close();
  }, [decision]);

  // Cada decisión nueva empieza limpia.
  useEffect(() => {
    setLibre("");
    setError(null);
  }, [decision?.clave]);

  async function enviar(accion: () => Promise<unknown>) {
    if (!decision) return;
    setEnviando(true);
    setError(null);
    try {
      await accion();
      setLiberado(PERSONAJES[decision.agente].nombre);
      const clave = decision.clave;
      // Un momento para ver que el personaje quedó libre antes de pasar a la siguiente.
      setTimeout(() => {
        setLiberado(null);
        onRespondida(clave);
      }, 1100);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar la respuesta");
    } finally {
      setEnviando(false);
    }
  }

  const p = decision ? PERSONAJES[decision.agente] : null;

  return (
    <dialog
      ref={dialogo}
      className="modal-decision"
      onClose={onCerrar}
      onClick={(e) => {
        // Clic en el fondo (fuera de la tarjeta) cierra.
        if (e.target === dialogo.current) onCerrar();
      }}
      aria-labelledby="titulo-decision"
    >
      {decision && p && (
        <div className="tarjeta-modal" style={{ ["--color-agente" as string]: p.color }}>
          <header className="cabecera-modal">
            <Retrato agente={decision.agente} tamano={56} />
            <div>
              <span className="etiqueta-subseccion">
                Prioridad {decision.prioridad} de {total}
              </span>
              <h2 id="titulo-decision">
                {decision.tipo === "aprobacion"
                  ? `${p.nombre} necesita tu aprobación`
                  : `${p.nombre} tiene una duda`}
              </h2>
            </div>
            <button type="button" className="cerrar-modal" onClick={onCerrar} aria-label="Cerrar">
              ×
            </button>
          </header>

          {liberado ? (
            <p className="liberado" role="status">
              ✓ Listo: {liberado} vuelve a trabajar.
            </p>
          ) : (
            <>
              {masUrgente && (
                <div className="aviso-urgente">
                  <span>
                    Hay una decisión más urgente: {PERSONAJES[masUrgente.agente].nombre} (prioridad 1).
                  </span>
                  <button type="button" onClick={() => onIrA(masUrgente.clave)}>
                    Responder esa primero
                  </button>
                </div>
              )}

              <dl className="contexto-modal">
                <dt>Encargo</dt>
                <dd>
                  <span className="mono">{decision.encargo.id}</span> · {decision.encargo.pedido.slice(0, 140)}
                  {decision.encargo.pedido.length > 140 ? "…" : ""}
                </dd>
                {decision.espec && (
                  <>
                    <dt>Especificación</dt>
                    <dd>
                      <span className="mono">{decision.espec.id}</span> · {decision.espec.titulo}
                    </dd>
                  </>
                )}
                <dt>Por qué va en este lugar</dt>
                <dd>{decision.motivo}</dd>
              </dl>

              {decision.tipo === "pregunta" && decision.pregunta && (
                <>
                  <p className="pregunta-modal">{decision.pregunta.texto}</p>
                  {decision.pregunta.propuesta && (
                    <div className="propuesta-modal">
                      <span className="etiqueta-subseccion">Propuesta del Diagnosticador</span>
                      <p>{decision.pregunta.propuesta}</p>
                    </div>
                  )}
                  <div className="opciones-modal">
                    {decision.pregunta.opciones.map((o) => (
                      <button
                        key={o}
                        type="button"
                        disabled={enviando}
                        onClick={() =>
                          enviar(() => responderPregunta(decision.encargo.id, decision.pregunta!.id, o))
                        }
                      >
                        {o}
                      </button>
                    ))}
                  </div>
                  <form
                    className="fila-alta"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const texto = libre.trim();
                      if (texto)
                        void enviar(() => responderPregunta(decision.encargo.id, decision.pregunta!.id, texto));
                    }}
                  >
                    <input
                      value={libre}
                      onChange={(e) => setLibre(e.target.value)}
                      placeholder="…o escribí tu propia respuesta"
                      aria-label="Respuesta libre"
                    />
                    <button type="submit" className="primario" disabled={enviando || !libre.trim()}>
                      Responder
                    </button>
                  </form>
                </>
              )}

              {decision.tipo === "aprobacion" && decision.espec && (
                <>
                  <p className="pregunta-modal">
                    Esta especificación toca algo delicado (borrar datos, dinero, permisos o producción).
                    ¿La construyo?
                  </p>
                  <p className="apagado">{decision.espec.descripcion}</p>
                  {decision.espec.archivos.length > 0 && (
                    <ul className="lista-archivos mono">
                      {decision.espec.archivos.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                  )}
                  <div className="opciones-modal">
                    <button
                      type="button"
                      className="primario"
                      disabled={enviando}
                      onClick={() =>
                        enviar(() => decidirEspecificacion(decision.encargo.id, decision.espec!.id, true))
                      }
                    >
                      Aprobar
                    </button>
                    <button
                      type="button"
                      disabled={enviando}
                      onClick={() =>
                        enviar(() => decidirEspecificacion(decision.encargo.id, decision.espec!.id, false))
                      }
                    >
                      Rechazar
                    </button>
                  </div>
                </>
              )}

              {error && <p className="error">{error}</p>}
            </>
          )}
        </div>
      )}
    </dialog>
  );
}
