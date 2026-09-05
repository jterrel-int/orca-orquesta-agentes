import type { Item, LadoBacklog, ResumenCorrida, Salud, TareaBacklog } from "./types";

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

export type { Item };
