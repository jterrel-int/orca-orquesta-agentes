import type {
  AnalisisRequisitos,
  ArchivoEjecucion,
  ModuloRequisitos,
  RespuestaRequisito,
  SugerenciasRequisitos,
  Ejecucion,
  ConfigFabrica,
  Encargo,
  EstadoAnthropic,
  EstadoRender,
  EstadoVercel,
  Integridad,
  MetricasEncargo,
  RegistroBitacora,
  Salud,
  SaludFabrica,
  UsoAnthropic,
} from "./types";

export const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/**
 * Token de acceso opcional (ORQUESTA_TOKEN en el backend). Vacío = backend
 * sin token, como en desarrollo local.
 */
export const TOKEN = process.env.NEXT_PUBLIC_ORQUESTA_TOKEN ?? "";

function cabecerasAcceso(): Record<string, string> {
  return TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
}

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${ruta}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...cabecerasAcceso(),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const detalle = await res.json().catch(() => null);
    throw new Error(detalle?.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const salud = () => pedir<Salud>("/api/health");

// --- conexión con Vercel (OAuth) ---

/** URL para abrir en una ventana emergente; el backend redirige a Vercel. */
export const urlConectarVercel = () =>
  `${API}/api/vercel/oauth/iniciar${TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : ""}`;

export const estadoVercel = () => pedir<EstadoVercel>("/api/vercel/estado");

export const desconectarVercel = () => pedir<void>("/api/vercel/conexion", { method: "DELETE" });

// --- conexión con Render (API key) ---

export const estadoRender = () => pedir<EstadoRender>("/api/render/estado");

export const conectarRender = (apiKey: string) =>
  pedir<EstadoRender>("/api/render/conexion", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });

export const desconectarRender = () => pedir<void>("/api/render/conexion", { method: "DELETE" });

// --- conexión con Anthropic (API key, no la sesión de claude.ai/Claude Code) ---

export const estadoAnthropic = () => pedir<EstadoAnthropic>("/api/anthropic/estado");

export const conectarAnthropic = (apiKey: string) =>
  pedir<EstadoAnthropic>("/api/anthropic/conexion", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });

export const desconectarAnthropic = () =>
  pedir<void>("/api/anthropic/conexion", { method: "DELETE" });

/** Contador local de tokens contra un límite propio — no el gasto real de la cuenta. */
export const usoAnthropic = () => pedir<UsoAnthropic | null>("/api/anthropic/uso");

export const establecerLimiteAnthropic = (limiteTokens: number) =>
  pedir<UsoAnthropic>("/api/anthropic/uso", {
    method: "PUT",
    body: JSON.stringify({ limite_tokens: limiteTokens }),
  });

// --- fábrica de software ---

/** Con `baseId`, una nueva versión que parte de los archivos de ese encargo. */
export const crearEncargo = (pedido: string, baseId?: string) =>
  pedir<Encargo>("/api/fabrica/encargos", {
    method: "POST",
    body: JSON.stringify({ pedido, base_id: baseId ?? null }),
  });

/** Los de la línea actual (sin los archivados por un reinicio). */
export const listarEncargos = () => pedir<Encargo[]>("/api/fabrica/encargos");

/** Detiene lo que corre y archiva los encargos actuales. No borra nada. */
export const reiniciarLinea = () =>
  pedir<{ archivados: string[]; detenidos: string[] }>("/api/fabrica/linea/reiniciar", {
    method: "POST",
  });

export const listarEjecuciones = () => pedir<Ejecucion[]>("/api/fabrica/ejecuciones");

export const archivosEjecucion = (id: string) =>
  pedir<ArchivoEjecucion[]>(`/api/fabrica/ejecuciones/${id}/archivos`);

export const leerArchivoEjecucion = (id: string, ruta: string) =>
  pedir<{ ruta: string; contenido: string }>(
    `/api/fabrica/ejecuciones/${id}/archivo?ruta=${encodeURIComponent(ruta)}`,
  );

export const obtenerEncargo = (id: string) => pedir<Encargo>(`/api/fabrica/encargos/${id}`);

export const responderPregunta = (id: string, preguntaId: string, respuesta: string) =>
  pedir<Encargo>(`/api/fabrica/encargos/${id}/preguntas/${preguntaId}`, {
    method: "POST",
    body: JSON.stringify({ respuesta }),
  });

export const decidirEspecificacion = (id: string, especId: string, aprobar: boolean) =>
  pedir<Encargo>(
    `/api/fabrica/encargos/${id}/especificaciones/${especId}/${aprobar ? "aprobar" : "rechazar"}`,
    { method: "POST" },
  );

export const reanudarEncargo = (id: string) =>
  pedir<Encargo>(`/api/fabrica/encargos/${id}/reanudar`, { method: "POST" });

/** Corta un encargo en marcha; queda interrumpido, listo para reanudar o cerrar. */
export const detenerEncargo = (id: string) =>
  pedir<Encargo>(`/api/fabrica/encargos/${id}/detener`, { method: "POST" });

/** Cierra el encargo con lo ya aprobado; lo pendiente queda sin terminar. */
export const finalizarEncargo = (id: string) =>
  pedir<Encargo>(`/api/fabrica/encargos/${id}/finalizar`, { method: "POST" });

// --- modo "diseñar por especificaciones" (backend/app/api/requisitos.py) ---

/** Determinista y sin LLM: se puede llamar en cada pausa del teclado. */
export const sugerirRequisitos = (requisitos: string[], borrador: string) =>
  pedir<SugerenciasRequisitos>("/api/fabrica/requisitos/sugerir", {
    method: "POST",
    body: JSON.stringify({ requisitos, borrador }),
  });

/** Usa el cerebro si hay uno (puede costar unos centavos). */
export const analizarRequisitos = (requisitos: string[], respuestas: RespuestaRequisito[]) =>
  pedir<AnalisisRequisitos>("/api/fabrica/requisitos/analizar", {
    method: "POST",
    body: JSON.stringify({ requisitos, respuestas }),
  });

export const componerPedido = (
  requisitos: string[],
  respuestas: RespuestaRequisito[],
  modulos: ModuloRequisitos[] | null,
  resumen: string,
) =>
  pedir<{ pedido: string }>("/api/fabrica/requisitos/componer", {
    method: "POST",
    body: JSON.stringify({ requisitos, respuestas, modulos, resumen }),
  });

export const bitacoraEncargo = (id: string) =>
  pedir<{ integridad: Integridad; registros: RegistroBitacora[] }>(
    `/api/fabrica/encargos/${id}/bitacora`,
  );

export const metricasEncargo = (id: string) =>
  pedir<MetricasEncargo>(`/api/fabrica/encargos/${id}/metricas`);

export const saludFabrica = () => pedir<SaludFabrica>("/api/fabrica/salud");

export interface EstadoCacheLLM {
  activa: boolean;
  entradas: number;
  aciertos: number;
  ahorro_estimado_usd: number;
  tokens_ahorrados: number;
}

export const estadoCacheLLM = () => pedir<EstadoCacheLLM>("/api/fabrica/cache");

export const limpiarCacheLLM = () =>
  pedir<{ borradas: number }>("/api/fabrica/cache/limpiar", { method: "POST" });

export const pluginsFabrica = () =>
  pedir<{ cargados: string[]; errores: string[] }>("/api/fabrica/plugins");

export const configFabrica = () => pedir<ConfigFabrica>("/api/fabrica/config");

/**
 * Extrae el texto de una especificación (.txt, .md, .pdf, .docx) para usarlo
 * como pedido. No crea el encargo: la persona lo revisa antes de encargar.
 * Va como multipart, por eso no usa `pedir` (que fuerza JSON).
 */
export async function importarDocumento(archivo: File): Promise<{ nombre: string; pedido: string }> {
  const datos = new FormData();
  datos.append("archivo", archivo);
  const res = await fetch(`${API}/api/fabrica/importar`, {
    method: "POST",
    body: datos,
    headers: cabecerasAcceso(),
  });
  if (!res.ok) {
    const detalle = await res.json().catch(() => null);
    throw new Error(detalle?.detail ?? `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as { nombre: string; pedido: string };
}
