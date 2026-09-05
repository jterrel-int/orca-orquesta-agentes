import type {
  EstadoRender,
  EstadoVercel,
  Item,
  LadoBacklog,
  ResumenCorrida,
  Salud,
  TareaBacklog,
} from "./types";

export const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${ruta}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const detalle = await res.json().catch(() => null);
    throw new Error(detalle?.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// --- corridas de agentes ---

export const lanzarCorrida = () =>
  pedir<{ status: string; detalle: string }>("/api/run", { method: "POST" });

export const estadoCorrida = () => pedir<ResumenCorrida | null>("/api/run/status");

export const salud = () => pedir<Salud>("/api/health");

// --- CRUD de items ---

export const listarItems = () => pedir<Item[]>("/api/items");

export const crearItem = (name: string) =>
  pedir<Item>("/api/items", { method: "POST", body: JSON.stringify({ name }) });

export const eliminarItem = (id: number) =>
  pedir<void>(`/api/items/${id}`, { method: "DELETE" });

// --- backlog ---

export const listarBacklog = () => pedir<TareaBacklog[]>("/api/backlog");

export const agregarTareaBacklog = (datos: {
  titulo: string;
  cuerpo: string;
  lado: LadoBacklog;
}) => pedir<TareaBacklog>("/api/backlog", { method: "POST", body: JSON.stringify(datos) });

// --- conexión con Vercel (OAuth) ---

/** URL para abrir en una ventana emergente; el backend redirige a Vercel. */
export const urlConectarVercel = () => `${API}/api/vercel/oauth/iniciar`;

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

export type { Item };
