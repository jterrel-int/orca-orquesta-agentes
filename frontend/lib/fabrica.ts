import type {
  Encargo,
  EstadoEncargo,
  EstadoEspec,
  Especificacion,
  EventoAgente,
  Pregunta,
} from "./types";

/** El orden del pipeline, tal como lo recorre el Líder (orchestrator/lider.py). */
export const ETAPAS_FABRICA = [
  { agente: "lider", etiqueta: "Líder" },
  { agente: "especificador", etiqueta: "Especificador" },
  { agente: "implementador", etiqueta: "Implementador" },
  { agente: "revisor", etiqueta: "Revisor" },
  { agente: "diagnosticador", etiqueta: "Diagnosticador" },
  { agente: "verificador", etiqueta: "Verificador" },
  { agente: "despliegue", etiqueta: "Despliegue" },
] as const;

export const ETIQUETA_ENCARGO: Record<EstadoEncargo, string> = {
  especificando: "Especificando",
  esperando_humano: "Espera decisión",
  en_curso: "En curso",
  terminado: "Terminado",
  fallido: "Fallido",
  interrumpido: "Interrumpido",
};

export const ETIQUETA_ESPEC: Record<EstadoEspec, string> = {
  pendiente: "Pendiente",
  esperando_aprobacion: "Espera aprobación",
  en_curso: "En curso",
  aprobada: "Aprobada",
  fallida: "Fallida",
  bloqueada: "Bloqueada",
};

/** Verde y rojo son estado, nunca decoración (ver globals.css). */
export function claseEncargo(estado: EstadoEncargo | EstadoEspec): string {
  if (estado === "terminado" || estado === "aprobada") return "ok";
  if (estado === "fallido" || estado === "fallida" || estado === "bloqueada") return "mal";
  if (estado === "esperando_humano" || estado === "esperando_aprobacion" || estado === "interrumpido")
    return "espera";
  return "neutro";
}

export function usd(valor: number | null | undefined): string {
  return valor == null ? "—" : `USD ${valor.toFixed(4)}`;
}

/** Las etapas que recorre cada especificación, en orden. */
export const ETAPAS_ESPEC = [
  { agente: "implementador", etiqueta: "Implementa" },
  { agente: "revisor", etiqueta: "Revisa" },
  { agente: "diagnosticador", etiqueta: "Diagnostica" },
  { agente: "verificador", etiqueta: "Verifica" },
] as const;

export type EstadoCelda = "pending" | "running" | "done" | "error";

export interface Carril {
  especId: string;
  etapas: Record<string, EstadoCelda>;
  activo: boolean;
  vioDiagnostico: boolean;
}

const PREFIJO_ESPEC = /^(S\d+)\b/;

/**
 * El contrato del WebSocket no tiene un campo de especificación (y no se
 * toca), pero el Líder empieza cada mensaje por especificación con su id
 * ("S2 · intento 1/2: …"). De ahí se reconstruye en qué etapa está cada una.
 * Una etapa posterior implica que las anteriores terminaron.
 */
export function derivarCarriles(
  eventos: EventoAgente[],
  especIds: string[],
  vivo = true,
): Map<string, Carril> {
  const orden = ETAPAS_ESPEC.map((e) => e.agente as string);
  const ultimo = new Map<string, EventoAgente>();
  const conDiagnostico = new Set<string>();
  for (const e of eventos) {
    const m = PREFIJO_ESPEC.exec(e.msg);
    if (!m || !orden.includes(e.agent)) continue;
    ultimo.set(m[1], e);
    if (e.agent === "diagnosticador") conDiagnostico.add(m[1]);
  }
  const carriles = new Map<string, Carril>();
  for (const id of especIds) {
    const etapas: Record<string, EstadoCelda> = {};
    const ev = ultimo.get(id);
    const indice = ev ? orden.indexOf(ev.agent) : -1;
    orden.forEach((agente, i) => {
      if (i < indice) etapas[agente] = agente === "diagnosticador" && !conDiagnostico.has(id) ? "pending" : "done";
      // Si el servidor dice que el encargo no corre, un "running" viejo no cuenta.
      else if (i === indice && ev) etapas[agente] = !vivo && ev.status === "running" ? "pending" : ev.status;
      else etapas[agente] = "pending";
    });
    carriles.set(id, {
      especId: id,
      etapas,
      activo: vivo && ev?.status === "running",
      vioDiagnostico: conDiagnostico.has(id),
    });
  }
  return carriles;
}

/** Profundidad en el grafo de dependencias: mismo nivel = puede ir en paralelo. */
export function nivelesDe(especs: Especificacion[]): Map<string, number> {
  const porId = new Map(especs.map((e) => [e.id, e]));
  const nivel = new Map<string, number>();
  const calcular = (id: string, visitando: Set<string>): number => {
    const conocido = nivel.get(id);
    if (conocido !== undefined) return conocido;
    if (visitando.has(id)) return 1;
    visitando.add(id);
    const deps = porId.get(id)?.depende_de.filter((d) => porId.has(d)) ?? [];
    const n = 1 + Math.max(0, ...deps.map((d) => calcular(d, visitando)));
    nivel.set(id, n);
    return n;
  };
  especs.forEach((e) => calcular(e.id, new Set()));
  return nivel;
}

/**
 * Cuántas instancias de cada agente están trabajando ahora, sumando todos los
 * encargos: cada (encargo, especificación) cuyo último evento es "running"
 * cuenta una. Solo encargos que el servidor reporta en marcha: un "running"
 * viejo de un encargo en pausa no es un agente trabajando.
 */
export function agentesVivos(eventos: EventoAgente[], corriendo: Set<string>): Map<string, number> {
  const ultimo = new Map<string, EventoAgente>();
  for (const e of eventos) {
    if (!e.run_id || !corriendo.has(e.run_id)) continue;
    const espec = PREFIJO_ESPEC.exec(e.msg)?.[1] ?? "-";
    // Por especificación, solo importa la etapa más reciente.
    const clave = espec === "-" ? `${e.run_id}|-|${e.agent}` : `${e.run_id}|${espec}`;
    ultimo.set(clave, e);
  }
  const conteo = new Map<string, number>();
  for (const e of ultimo.values()) {
    if (e.status === "running") conteo.set(e.agent, (conteo.get(e.agent) ?? 0) + 1);
  }
  return conteo;
}

// --- decisiones humanas: quién espera una respuesta y en qué orden ---

export type TipoDecision = "pregunta" | "aprobacion";

export interface Decision {
  /** Única en toda la cola: sirve de key y para recordar cuál se está respondiendo. */
  clave: string;
  tipo: TipoDecision;
  /** El agente que "pregunta": es sobre quien aparece el foquito. */
  agente: "especificador" | "diagnosticador" | "lider";
  encargo: Encargo;
  pregunta?: Pregunta;
  espec?: Especificacion;
  /** 1 = la más urgente de toda la fábrica. */
  prioridad: number;
  /** Por qué va en ese lugar, en una frase. */
  motivo: string;
}

const RANGO = { especificador: 0, diagnosticador: 1, lider: 2 } as const;

const MOTIVO = {
  especificador: "Frena el encargo completo: no hay especificaciones hasta que respondas.",
  diagnosticador: "Frena esta especificación y todas las que dependen de ella.",
  lider: "Solo espera esta especificación; las demás siguen avanzando.",
} as const;

/**
 * Todas las decisiones pendientes, ordenadas por cuánto trabajo frenan:
 * primero las preguntas del Especificador, después las del Diagnosticador y
 * al final las aprobaciones del Líder. A igual tipo, el encargo más antiguo
 * primero, y dentro del encargo, en el orden en que aparecen.
 */
export function decisionesPendientes(encargos: Encargo[]): Decision[] {
  const sueltas: Omit<Decision, "prioridad">[] = [];
  for (const encargo of encargos) {
    for (const p of encargo.preguntas) {
      if (p.respuesta !== null) continue;
      const agente = p.origen === "diagnosticador" ? "diagnosticador" : "especificador";
      sueltas.push({
        clave: `${encargo.id}|p|${p.id}`,
        tipo: "pregunta",
        agente,
        encargo,
        pregunta: p,
        espec: p.espec_id ? encargo.especificaciones.find((e) => e.id === p.espec_id) : undefined,
        motivo: MOTIVO[agente],
      });
    }
    for (const e of encargo.especificaciones) {
      if (e.estado !== "esperando_aprobacion") continue;
      sueltas.push({
        clave: `${encargo.id}|a|${e.id}`,
        tipo: "aprobacion",
        agente: "lider",
        encargo,
        espec: e,
        motivo: MOTIVO.lider,
      });
    }
  }
  const orden = new Map(sueltas.map((d, i) => [d.clave, i]));
  sueltas.sort(
    (a, b) =>
      RANGO[a.agente] - RANGO[b.agente] ||
      a.encargo.creado_en.localeCompare(b.encargo.creado_en) ||
      (orden.get(a.clave) ?? 0) - (orden.get(b.clave) ?? 0),
  );
  return sueltas.map((d, i) => ({ ...d, prioridad: i + 1 }));
}
