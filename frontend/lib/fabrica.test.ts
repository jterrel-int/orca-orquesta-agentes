import { describe, expect, it } from "vitest";
import { agentesVivos, decisionesPendientes } from "./fabrica";
import type { Encargo, Especificacion, EventoAgente, Pregunta } from "./types";

function espec(id: string, estado: Especificacion["estado"] = "pendiente"): Especificacion {
  return {
    id,
    titulo: id,
    descripcion: "",
    criterios: [],
    archivos: [],
    depende_de: [],
    requiere_aprobacion: estado === "esperando_aprobacion",
    e2e: false,
    estado,
    intentos: 0,
    motivo: "",
    aprobada_por_humano: false,
  };
}

function pregunta(id: string, origen: Pregunta["origen"], respuesta: string | null = null): Pregunta {
  return { id, texto: id, opciones: [], respuesta, origen, espec_id: origen === "diagnosticador" ? "S2" : null };
}

function encargo(id: string, creado: string, datos: Partial<Encargo> = {}): Encargo {
  return {
    id,
    pedido: id,
    estado: "esperando_humano",
    especificaciones: [],
    preguntas: [],
    costo_usd: 0,
    motivo: "",
    url_despliegue: null,
    creado_en: creado,
    actualizado_en: creado,
    corriendo: false,
    version: 1,
    padre_id: null,
    raiz_id: null,
    linaje: id,
    archivado_en: null,
    ...datos,
  };
}

describe("decisionesPendientes", () => {
  it("prioriza lo que más trabajo frena y, a igual tipo, el encargo más antiguo", () => {
    const viejo = encargo("viejo", "2026-09-01T10:00:00Z", {
      especificaciones: [espec("S1", "aprobada"), espec("S3", "esperando_aprobacion")],
    });
    const nuevo = encargo("nuevo", "2026-09-02T10:00:00Z", {
      especificaciones: [espec("S2", "pendiente"), espec("S4", "esperando_aprobacion")],
      preguntas: [pregunta("D-S2-2", "diagnosticador"), pregunta("P-ya", "especificador", "listo")],
    });
    const otro = encargo("otro", "2026-09-03T10:00:00Z", {
      preguntas: [pregunta("P-tabla", "especificador")],
    });

    const cola = decisionesPendientes([viejo, nuevo, otro]);

    expect(cola.map((d) => [d.prioridad, d.agente, d.encargo.id])).toEqual([
      [1, "especificador", "otro"], // frena un encargo entero, aunque sea el más nuevo
      [2, "diagnosticador", "nuevo"],
      [3, "lider", "viejo"], // aprobaciones: el encargo más antiguo primero
      [4, "lider", "nuevo"],
    ]);
    expect(cola[1].espec?.id).toBe("S2");
    expect(cola.every((d) => d.motivo.length > 0)).toBe(true);
  });

  it("sin nada pendiente, la cola está vacía", () => {
    expect(decisionesPendientes([encargo("x", "2026-09-01T00:00:00Z", { estado: "terminado" })])).toEqual([]);
  });
});

describe("agentesVivos", () => {
  const ev = (agent: string, status: EventoAgente["status"], msg: string, run_id = "e1"): EventoAgente => ({
    agent,
    status,
    msg,
    ts: "",
    run_id,
    artifacts: [],
  });

  it("cuenta una instancia por especificación y solo en encargos que corren", () => {
    const eventos = [
      ev("implementador", "running", "S2 · intento 1/2: a"),
      ev("implementador", "running", "S3 · intento 1/2: b"),
      ev("implementador", "done", "S3 · intento 1/2: 2 archivo(s)"),
      ev("revisor", "running", "S3 · intento 1/2: revisando"),
      ev("lider", "running", "Encargo e2 en marcha", "e2"),
    ];
    const vivos = agentesVivos(eventos, new Set(["e1"]));
    expect(Object.fromEntries(vivos)).toEqual({ implementador: 1, revisor: 1 });
  });
});
