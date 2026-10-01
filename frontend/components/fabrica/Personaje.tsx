"use client";

import {
  BadgeCheck,
  ClipboardList,
  Crown,
  HardHat,
  Lightbulb,
  type LucideIcon,
  Rocket,
  ScanSearch,
  Stethoscope,
} from "lucide-react";

/**
 * Los siete agentes de la fábrica.
 *
 * Avatares: DiceBear, estilo "Notionists" de Zoish (licencia CC0 1.0: uso
 * libre, sin atribución obligatoria). Se generan al compilar con
 * `npm run avatares` (scripts/generar-avatares.mjs) en public/agentes/, no
 * en el navegador: la librería pesa ~120 kB y las caras nunca cambian.
 *
 * La identidad nunca depende solo del color: cada uno tiene su cara, su
 * gesto, un icono de oficio (Lucide) y su nombre escrito.
 */

export type AgenteOficina =
  | "lider"
  | "especificador"
  | "implementador"
  | "revisor"
  | "diagnosticador"
  | "verificador"
  | "despliegue";

export type EstadoPersonaje = "libre" | "trabajando" | "esperando";

interface FichaPersonaje {
  nombre: string;
  oficio: string;
  color: string;
  icono: LucideIcon;
}

export const PERSONAJES: Record<AgenteOficina, FichaPersonaje> = {
  lider: {
    nombre: "Líder",
    oficio: "Dirige la orquesta: decide el orden, reintenta y te pide aprobación",
    color: "var(--agente-lider)",
    icono: Crown,
  },
  especificador: {
    nombre: "Especificador",
    oficio: "Parte tu pedido en especificaciones y pregunta si algo es ambiguo",
    color: "var(--agente-especificador)",
    icono: ClipboardList,
  },
  implementador: {
    nombre: "Implementador",
    oficio: "Construye el código y sus pruebas",
    color: "var(--agente-implementador)",
    icono: HardHat,
  },
  revisor: {
    nombre: "Revisor",
    oficio: "Corre las pruebas y valida contra la especificación",
    color: "var(--agente-revisor)",
    icono: ScanSearch,
  },
  diagnosticador: {
    nombre: "Diagnosticador",
    oficio: "Aparece si hay un rechazo: ¿falló el código, la especificación o el entorno?",
    color: "var(--agente-diagnosticador)",
    icono: Stethoscope,
  },
  verificador: {
    nombre: "Verificador",
    oficio: "Revisa que todo lo público tenga prueba y corre las pruebas funcionales",
    color: "var(--agente-verificador)",
    icono: BadgeCheck,
  },
  despliegue: {
    nombre: "Despliegue",
    oficio: "Prepara el CI y publica en GitHub (simulado mientras esté apagado)",
    color: "var(--agente-despliegue)",
    icono: Rocket,
  },
};

/** Avatar con su insignia de oficio. Para leyenda, cola y modal. */
export function Retrato({ agente, tamano = 44 }: { agente: AgenteOficina; tamano?: number }) {
  const p = PERSONAJES[agente];
  const Icono = p.icono;
  return (
    <span
      className="retrato"
      style={{ width: tamano, height: tamano, ["--color-agente" as string]: p.color }}
      aria-hidden
    >
      <img src={`/agentes/${agente}.svg`} alt="" width={tamano} height={tamano} />
      <span className="insignia-oficio">
        <Icono size={Math.max(10, Math.round(tamano * 0.24))} strokeWidth={2.4} />
      </span>
    </span>
  );
}

/**
 * Un puesto de trabajo en el piso de la oficina: el agente con su anillo de
 * estado, su escritorio y, encima, lo que está haciendo — pensando si
 * trabaja, un foquito con su lugar en la cola si espera una respuesta.
 */
export default function Personaje({
  agente,
  estado,
  instancias,
  prioridad,
  pendientes,
  onAbrir,
}: {
  agente: AgenteOficina;
  estado: EstadoPersonaje;
  instancias: number;
  /** La prioridad de su decisión más urgente (1 = la más urgente de todas). */
  prioridad: number | null;
  /** Cuántas decisiones tiene esperando. */
  pendientes: number;
  onAbrir: () => void;
}) {
  const p = PERSONAJES[agente];
  const esperando = estado === "esperando";
  const etiqueta = esperando
    ? `${p.nombre}: necesita tu respuesta, prioridad ${prioridad}${pendientes > 1 ? ` (${pendientes} pendientes)` : ""}. Abrir.`
    : `${p.nombre}: ${estado === "trabajando" ? "trabajando" : "libre"}`;

  const cuerpo = (
    <>
      <span className="anillo-estado">
        <Retrato agente={agente} tamano={84} />
      </span>
      <span className="escritorio" aria-hidden />
      <strong className="nombre-puesto">{p.nombre}</strong>
    </>
  );

  return (
    <div className={`puesto ${estado}`} style={{ ["--color-agente" as string]: p.color }}>
      <div className="indicador-puesto">
        {estado === "trabajando" && (
          <span className="pensando" title={`${p.nombre} está trabajando`} aria-hidden>
            <i />
            <i />
            <i />
            {instancias > 1 && <b>×{instancias}</b>}
          </span>
        )}
        {esperando && (
          <button type="button" className="foquito-boton" onClick={onAbrir} aria-label={etiqueta}>
            <Lightbulb size={22} strokeWidth={2.2} />
            {prioridad !== null && <span className="numero-prioridad">{prioridad}</span>}
            {pendientes > 1 && <span className="pendientes-extra">×{pendientes}</span>}
          </button>
        )}
      </div>
      {esperando ? (
        // Todo el puesto se puede tocar; el foquito es el control con foco de teclado.
        <button type="button" className="puesto-cuerpo" onClick={onAbrir} aria-hidden tabIndex={-1}>
          {cuerpo}
        </button>
      ) : (
        <div className="puesto-cuerpo" role="img" aria-label={etiqueta}>
          {cuerpo}
        </div>
      )}
    </div>
  );
}
