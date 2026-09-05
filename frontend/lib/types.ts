export type EstadoAgente = "pending" | "running" | "done" | "error";

/** Formato de los mensajes del WebSocket. Espeja backend/app/models/eventos.py */
export interface EventoAgente {
  agent: string;
  status: EstadoAgente;
  msg: string;
  ts: string;
  run_id?: string | null;
  artifacts?: string[];
}

export interface ResumenAgente {
  agent: string;
  status: EstadoAgente;
  ultimo_msg: string;
  duracion_s: number | null;
}

export interface ResumenCorrida {
  run_id: string;
  status: "running" | "done" | "error";
  agentes: ResumenAgente[];
  iniciado_en: string;
  terminado_en: string | null;
}

export interface Item {
  id: number;
  name: string;
  creado_en: string;
}

/** Espeja el cuerpo de GET /api/health. */
export interface Salud {
  ok: boolean;
  brain: string;
  deploy_enabled: boolean;
  conexiones_ws: number;
  /** Configuración que arrancó igual pero probablemente no es la esperada. */
  advertencias: string[];
}

/** Los agentes que el dashboard muestra, en el orden del pipeline. */
export const AGENTES = ["backend", "frontend", "deploy"] as const;
