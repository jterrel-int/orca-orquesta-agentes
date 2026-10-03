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

/** Espeja el cuerpo de GET /api/health. */
export interface Salud {
  ok: boolean;
  brain: string;
  /** "anthropic" | "scripted" | "claude-cli" — qué cerebro está activo ahora mismo. */
  cerebro_activo: string;
  cerebro_modelo: string | null;
  /**
   * "guardada en Configuración" | "variable de entorno ANTHROPIC_API_KEY" |
   * el comando del CLI (si cerebro_activo es "claude-cli") | null.
   */
  cerebro_fuente: string | null;
  /** Email logueado en el CLI, solo si cerebro_activo es "claude-cli"; si no, null. */
  cerebro_cuenta: string | null;
  deploy_enabled: boolean;
  conexiones_ws: number;
  /** Configuración que arrancó igual pero probablemente no es la esperada. */
  advertencias: string[];
  vercel_token_configurado: boolean;
  origenes_permitidos: string[];
}

/**
 * Contador local de tokens contra un límite que define el usuario — Anthropic
 * no expone el gasto real de la cuenta a una API key normal, así que esto no
 * es "cuánto llevás gastado en tu cuenta", sino un tope propio para saber
 * cuándo frenar. Espeja GET/PUT /api/anthropic/uso.
 */
export interface UsoAnthropic {
  limite_tokens: number;
  tokens_usados: number;
  porcentaje: number;
}

/** Espeja GET /api/anthropic/estado y la respuesta de POST /api/anthropic/conexion. */
export interface EstadoAnthropic {
  conectado: boolean;
  modelo: string;
  /** Los últimos caracteres de la key, nunca la key completa. */
  clave?: string;
  uso: UsoAnthropic | null;
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

// --- fábrica de software (backend/app/api/fabrica.py) ---

export type EstadoEspec =
  | "pendiente"
  | "esperando_aprobacion"
  | "en_curso"
  | "aprobada"
  | "fallida"
  | "bloqueada";

export type EstadoEncargo =
  | "especificando"
  | "esperando_humano"
  | "en_curso"
  | "terminado"
  | "fallido"
  | "interrumpido";

export interface Especificacion {
  id: string;
  titulo: string;
  descripcion: string;
  criterios: string[];
  archivos: string[];
  depende_de: string[];
  requiere_aprobacion: boolean;
  e2e: boolean;
  estado: EstadoEspec;
  intentos: number;
  motivo: string;
  aprobada_por_humano: boolean;
  /** Intentos sumando todas las rondas (los reintentos humanos no lo reinician). */
  rondas?: number;
  /** "" = normal; "reescritura" = tras un atasco, se reescribe desde cero. */
  estrategia?: string;
}

export interface Pregunta {
  id: string;
  texto: string;
  opciones: string[];
  respuesta: string | null;
  origen: "especificador" | "diagnosticador";
  espec_id: string | null;
  /** La solución que sugirió el Diagnosticador, si la hubo. */
  propuesta?: string | null;
}

export interface Encargo {
  id: string;
  pedido: string;
  estado: EstadoEncargo;
  especificaciones: Especificacion[];
  preguntas: Pregunta[];
  costo_usd: number;
  motivo: string;
  url_despliegue: string | null;
  creado_en: string;
  actualizado_en: string;
  corriendo: boolean;
  /** Versionado: una iteración parte de los archivos de su padre. */
  version: number;
  padre_id: string | null;
  raiz_id: string | null;
  /** Id de la v1: agrupa todas las versiones de un mismo producto. */
  linaje: string;
  /** Si se archivó al reiniciar la línea. */
  archivado_en: string | null;
}

export interface MetricaEtapa {
  encargo_id: string;
  etapa: string;
  agente: string;
  resultado: string;
  duracion_s: number;
  espec_id: string | null;
  intento: number;
  modelo: string;
  tokens_entrada: number;
  tokens_salida: number;
  costo_usd: number | null;
  ts: string;
}

export interface MetricasEncargo {
  etapas: MetricaEtapa[];
  costo_total_usd: number;
  costo_completo: boolean;
  duracion_total_s: number;
  tokens_total: number;
}

export interface Integridad {
  integra: boolean;
  registros: number;
  primer_registro_roto: number | null;
}

export interface RegistroBitacora {
  secuencia: number;
  encargo_id: string;
  agente: string;
  accion: string;
  evidencia: Record<string, unknown>;
  ts: string;
  hash_previo: string;
  hash: string;
}

export type NivelSalud = "ok" | "atencion" | "critico";

export interface SaludFabrica {
  signos: {
    estado_general: NivelSalud;
    encargos_total: number;
    encargos_24h: number;
    encargos_activos: number;
    esperando_humano: number;
    especificaciones_aprobadas: number;
    especificaciones_fallidas: number;
    tasa_aprobacion_primer_intento: number | null;
    rechazos_por_causa: Record<string, number>;
    costo_total_usd: number;
    costo_promedio_encargo_usd: number | null;
    duracion_media_por_etapa_s: Record<string, number>;
    costo_por_etapa_usd: Record<string, number>;
    bitacora_integra: boolean;
    alertas: { nivel: NivelSalud; signo: string; mensaje: string }[];
  };
  velocidad: {
    dia: string;
    encargos: number;
    especificaciones_aprobadas: number;
    costo_usd: number;
    duracion_total_s: number;
  }[];
  integridad: Integridad;
}

export interface ConfigFabrica {
  paralelismo: number;
  orquestador: "local" | "prefect";
  prefect_ui_url: string | null;
  aprobacion_humana: "nunca" | "ambiguedad" | "siempre";
  max_intentos: number;
  max_rondas?: number;
  timeout_etapa_s?: number;
  presupuesto_usd: number;
  cache_llm: boolean;
}

/** Una ejecución: su carpeta en fabrica_espacios/ cruzada con su encargo. */
export interface Ejecucion {
  id: string;
  en_base: boolean;
  carpeta: boolean;
  pedido: string | null;
  estado: EstadoEncargo | null;
  version: number;
  padre_id: string | null;
  raiz_id: string | null;
  archivado_en: string | null;
  creado_en: string | null;
  costo_usd: number;
  especificaciones: number;
  aprobadas: number;
  archivos: number;
  bytes: number;
  modificado_en: string | null;
  corriendo: boolean;
}

export interface ArchivoEjecucion {
  ruta: string;
  bytes: number;
}

// --- modo "diseñar por especificaciones" (backend/app/dominio/requisitos.py) ---

export interface IntencionRequisitos {
  dominio: string | null;
  nombre: string;
  resumen: string;
  /** 0..1: cuánto se parece a un tipo de proyecto conocido. */
  confianza: number;
  entidades: string[];
}

export interface SugerenciasRequisitos {
  intencion: IntencionRequisitos;
  /** Cómo completar la frase que se está escribiendo. */
  autocompletado: string[];
  /** Requisitos típicos de este tipo de proyecto que todavía faltan. */
  sugerencias: string[];
}

export interface ModuloRequisitos {
  nombre: string;
  /** Posiciones en la lista de requisitos. */
  requisitos: number[];
}

export interface PreguntaRequisitos {
  id: string;
  categoria: string;
  texto: string;
  porque: string;
  opciones: string[];
  recomendada: number;
}

export interface RecomendacionRequisitos {
  texto: string;
  categoria: string;
  porque: string;
}

export interface RespuestaRequisito {
  categoria: string;
  pregunta: string;
  respuesta: string;
}

export type CoberturaCategoria = "clara" | "parcial" | "falta" | "resuelta";

export interface AnalisisRequisitos {
  intencion: IntencionRequisitos;
  modulos: ModuloRequisitos[];
  cobertura: Record<string, CoberturaCategoria>;
  preguntas: PreguntaRequisitos[];
  recomendaciones: RecomendacionRequisitos[];
  listo: boolean;
  origen: "heuristica" | "cerebro";
  costo_usd: number | null;
  modelo: string;
}
