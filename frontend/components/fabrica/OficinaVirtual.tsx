"use client";

import Link from "next/link";
import { ChevronRight, CornerRightDown, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { reiniciarLinea } from "@/lib/api";
import { agentesVivos, type Decision, decisionesPendientes } from "@/lib/fabrica";
import type { Encargo, EventoAgente } from "@/lib/types";
import ModalDecision from "./ModalDecision";
import Personaje, {
  type AgenteOficina,
  type EstadoPersonaje,
  PERSONAJES,
  Retrato,
} from "./Personaje";

/**
 * La oficina de la fábrica: los siete agentes en sus puestos, en el orden del
 * pipeline. Trabajando, piensan; si esperan una respuesta, se les prende un
 * foquito con su lugar en la cola. Clic en el foquito → modal → respuesta →
 * el agente vuelve a trabajar.
 *
 * El Diagnosticador no está en la línea: es efímero (solo aparece si el
 * Revisor rechaza algo), así que tiene su consultorio aparte.
 */

/** La línea principal, en el orden en que un encargo la recorre. */
const LINEA: AgenteOficina[] = [
  "lider",
  "especificador",
  "implementador",
  "revisor",
  "verificador",
  "despliegue",
];

const ORDEN: AgenteOficina[] = [
  "lider",
  "especificador",
  "implementador",
  "revisor",
  "verificador",
  "despliegue",
  "diagnosticador",
];

const ETIQUETA_ESTADO: Record<EstadoPersonaje, string> = {
  libre: "Libre",
  trabajando: "Trabajando",
  esperando: "Espera tu respuesta",
};

export default function OficinaVirtual({
  encargos,
  eventos,
  onCambio,
}: {
  encargos: Encargo[];
  eventos: EventoAgente[];
  /** Recarga la lista de encargos. */
  onCambio: () => void;
}) {
  const corriendo = useMemo(
    () => new Set(encargos.filter((e) => e.corriendo).map((e) => e.id)),
    [encargos],
  );
  const vivos = useMemo(() => agentesVivos(eventos, corriendo), [eventos, corriendo]);
  const decisiones = useMemo(() => decisionesPendientes(encargos), [encargos]);
  const porAgente = useMemo(() => {
    const mapa = new Map<AgenteOficina, Decision[]>();
    for (const d of decisiones) mapa.set(d.agente, [...(mapa.get(d.agente) ?? []), d]);
    return mapa;
  }, [decisiones]);

  const [abierta, setAbierta] = useState<string | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [reiniciando, setReiniciando] = useState(false);
  const [avisoReinicio, setAvisoReinicio] = useState<string | null>(null);

  async function reiniciar() {
    setReiniciando(true);
    try {
      const r = await reiniciarLinea();
      setAvisoReinicio(
        r.archivados.length === 0
          ? "La línea ya estaba vacía."
          : `Línea reiniciada: ${r.archivados.length} encargo(s) archivado(s)` +
              (r.detenidos.length ? `, ${r.detenidos.length} detenido(s)` : "") +
              ". Siguen en Ejecuciones.",
      );
      setAbierta(null);
      onCambio();
    } catch (e) {
      setAvisoReinicio(e instanceof Error ? e.message : "No se pudo reiniciar la línea");
    } finally {
      setReiniciando(false);
      setConfirmando(false);
    }
  }

  /**
   * Después de responder: la siguiente de la cola (elegida con la cola que ya
   * tenemos, así el modal no se cierra y reabre mientras llega la recarga), y
   * se recarga en paralelo para que el foquito respondido se apague.
   */
  function avanzar(respondida: string) {
    setAbierta(decisiones.find((d) => d.clave !== respondida)?.clave ?? null);
    onCambio();
  }

  function estadoDe(agente: AgenteOficina): EstadoPersonaje {
    if (porAgente.has(agente)) return "esperando";
    if ((vivos.get(agente) ?? 0) > 0) return "trabajando";
    return "libre";
  }

  // Instancias, no personajes: la misma cuenta que la portada ("×2" de un
  // Revisor que revisa dos especificaciones cuenta dos).
  const trabajando = [...vivos.values()].reduce((a, b) => a + b, 0);
  const decisionAbierta = decisiones.find((d) => d.clave === abierta) ?? null;
  const primera = decisiones[0] ?? null;

  return (
    <section className="oficina" aria-label="Oficina de la fábrica">
      <div className="oficina-cabecera">
        <div>
          <span className="etiqueta-subseccion">La oficina</span>
          <p className="oficina-resumen">
            {decisiones.length > 0 ? (
              <>
                <strong>{decisiones.length}</strong>{" "}
                {decisiones.length === 1 ? "decisión espera" : "decisiones esperan"} tu respuesta ·{" "}
              </>
            ) : null}
            <strong>{trabajando}</strong> {trabajando === 1 ? "agente trabajando" : "agentes trabajando"}
            {decisiones.length === 0 && trabajando === 0 && " · encarga algo arriba y mira cómo se ponen a trabajar"}
          </p>
        </div>
        <div className="acciones-oficina">
          {primera && (
            <button type="button" className="primario" onClick={() => setAbierta(primera.clave)}>
              Responder en orden ({decisiones.length})
            </button>
          )}
          <button
            type="button"
            className="boton-reiniciar"
            onClick={() => setConfirmando(true)}
            disabled={confirmando || reiniciando || encargos.length === 0}
            title={encargos.length === 0 ? "La línea ya está vacía" : undefined}
          >
            <RotateCcw size={16} aria-hidden /> Reiniciar línea
          </button>
        </div>
      </div>

      {confirmando && (
        <div className="confirmar-reinicio" role="alertdialog" aria-labelledby="titulo-reinicio">
          <div>
            <strong id="titulo-reinicio">¿Reiniciar la línea de producción?</strong>
            <p>
              Se detienen los encargos en curso y se archivan los {encargos.length} de la línea. No se
              borra nada: siguen en{" "}
              <Link href="/fabrica/ejecuciones">Ejecuciones</Link>, desde donde puedes reanudarlos o
              crear una nueva versión.
            </p>
          </div>
          <div className="fila-alta">
            <button type="button" className="primario" onClick={reiniciar} disabled={reiniciando}>
              {reiniciando ? "Reiniciando…" : "Sí, reiniciar"}
            </button>
            <button type="button" onClick={() => setConfirmando(false)} disabled={reiniciando}>
              Cancelar
            </button>
          </div>
        </div>
      )}
      {avisoReinicio && !confirmando && (
        <p className="aviso-reinicio" role="status">
          {avisoReinicio}{" "}
          <button type="button" className="enlace" onClick={() => setAvisoReinicio(null)}>
            Cerrar
          </button>
        </p>
      )}

      <div className="oficina-lienzo">
        <div className="piso" role="group" aria-label="Los siete agentes en sus puestos">
          <div className="linea-principal">
            <span className="rotulo-zona">Línea de producción</span>
            <div className="puestos">
              {LINEA.map((agente, i) => {
                const cola = porAgente.get(agente) ?? [];
                return (
                  <div key={agente} className="celda-puesto">
                    <Personaje
                      agente={agente}
                      estado={estadoDe(agente)}
                      instancias={vivos.get(agente) ?? 0}
                      prioridad={cola[0]?.prioridad ?? null}
                      pendientes={cola.length}
                      onAbrir={() => cola[0] && setAbierta(cola[0].clave)}
                    />
                    {i < LINEA.length - 1 && (
                      <ChevronRight className="conector" size={22} strokeWidth={2.5} aria-hidden />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          <div className="consultorio">
            <span className="rotulo-zona">Consultorio</span>
            <span className="nota-consultorio">
              <CornerRightDown size={14} aria-hidden /> si el Revisor rechaza algo
            </span>
            {(() => {
              const cola = porAgente.get("diagnosticador") ?? [];
              return (
                <Personaje
                  agente="diagnosticador"
                  estado={estadoDe("diagnosticador")}
                  instancias={vivos.get("diagnosticador") ?? 0}
                  prioridad={cola[0]?.prioridad ?? null}
                  pendientes={cola.length}
                  onAbrir={() => cola[0] && setAbierta(cola[0].clave)}
                />
              );
            })()}
          </div>
        </div>
      </div>

      <div className="oficina-pie">
        <ul className="leyenda-personajes" aria-label="Quién es quién">
          {ORDEN.map((agente) => {
            const p = PERSONAJES[agente];
            const estado = estadoDe(agente);
            return (
              <li key={agente} className={`leyenda-item ${estado}`}>
                <Retrato agente={agente} />
                <div>
                  <strong>{p.nombre}</strong>
                  <span className={`chip-estado ${estado}`}>
                    {ETIQUETA_ESTADO[estado]}
                    {estado === "trabajando" && (vivos.get(agente) ?? 0) > 1 ? ` ×${vivos.get(agente)}` : ""}
                  </span>
                  <p>{p.oficio}</p>
                </div>
              </li>
            );
          })}
        </ul>

        {decisiones.length > 0 && (
          <aside className="cola-decisiones" aria-label="Cola de respuestas">
            <span className="etiqueta-subseccion">Cola de respuestas</span>
            <p className="apagado">
              Primero lo que más trabajo frena: preguntas del Especificador, después del Diagnosticador y
              al final las aprobaciones del Líder. A igual tipo, el encargo más antiguo.
            </p>
            <ol>
              {decisiones.map((d) => (
                <li key={d.clave}>
                  <span className="numero-cola">{d.prioridad}</span>
                  <Retrato agente={d.agente} tamano={32} />
                  <span className="texto-cola">
                    <strong>{PERSONAJES[d.agente].nombre}</strong>
                    <span>
                      {d.tipo === "aprobacion" ? `Aprobar ${d.espec?.id}` : "Duda"} · encargo{" "}
                      <span className="mono">{d.encargo.id}</span>
                    </span>
                  </span>
                  <button type="button" onClick={() => setAbierta(d.clave)}>
                    Responder
                  </button>
                </li>
              ))}
            </ol>
          </aside>
        )}
      </div>

      <p className="credito-avatares">
        Avatares:{" "}
        <a href="https://www.dicebear.com/styles/notionists/" target="_blank" rel="noreferrer">
          Notionists
        </a>{" "}
        de Zoish vía DiceBear (CC0) · iconos: Lucide
      </p>

      <ModalDecision
        decision={decisionAbierta}
        total={decisiones.length}
        masUrgente={primera && decisionAbierta && primera.clave !== decisionAbierta.clave ? primera : null}
        onCerrar={() => setAbierta(null)}
        onRespondida={avanzar}
        onIrA={setAbierta}
      />
    </section>
  );
}
