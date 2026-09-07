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
  /** Qué caso de uso lanzó esta corrida; null/ausente es el CRUD de Items. */
  caso_de_uso?: string | null;
}

/** Espeja GET /api/casos-de-uso. */
export interface CasoDeUso {
  id: string;
  nombre: string;
  descripcion: string;
  icono: string;
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
  vercel_token_configurado: boolean;
  origenes_permitidos: string[];
}

/** Los agentes que el dashboard muestra, en el orden del pipeline. */
export const AGENTES = ["backend", "frontend", "deploy"] as const;

export type LadoBacklog = "BE" | "FE" | "DE";

/** Espeja una tarea parseada de docs/BACKLOG.md. */
export interface TareaBacklog {
  id: string;
  titulo: string;
  cuerpo: string;
  lado: LadoBacklog;
}

/** Espeja GET /api/vercel/estado. */
export interface EstadoVercel {
  conectado: boolean;
  team_id: string | null;
}

/** Espeja GET /api/render/estado y la respuesta de POST /api/render/conexion. */
export interface EstadoRender {
  conectado: boolean;
  email?: string | null;
  nombre?: string | null;
  servicio_url?: string | null;
  servicio_suspendido?: string | null;
  advertencia?: string;
}
