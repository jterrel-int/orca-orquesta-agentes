"use client";

import { ArrowLeft, Check, Lightbulb, Plus, RefreshCw, Sparkles, Wand2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { analizarRequisitos, componerPedido, sugerirRequisitos } from "@/lib/api";
import { CATEGORIAS_REQUISITOS, ETIQUETA_COBERTURA } from "@/lib/fabrica";
import type {
  AnalisisRequisitos,
  PreguntaRequisitos,
  RespuestaRequisito,
  SugerenciasRequisitos,
} from "@/lib/types";

type Fase = "escribir" | "revisar" | "pedido";

const CLAVE_BORRADOR = "orquesta.disenador.v1";
const PASOS: { fase: Fase; etiqueta: string }[] = [
  { fase: "escribir", etiqueta: "Describe tu idea" },
  { fase: "revisar", etiqueta: "Revisa y completa" },
  { fase: "pedido", etiqueta: "Encarga" },
];

interface Borrador {
  requisitos: string[];
  respuestas: Record<string, RespuestaRequisito>;
}

function leerBorrador(): Borrador {
  try {
    const crudo = localStorage.getItem(CLAVE_BORRADOR);
    if (crudo) return JSON.parse(crudo) as Borrador;
  } catch {
    // Sin almacenamiento (ventana privada, vista previa): se arranca vacío.
  }
  return { requisitos: [], respuestas: {} };
}

function guardarBorrador(b: Borrador) {
  try {
    localStorage.setItem(CLAVE_BORRADOR, JSON.stringify(b));
  } catch {
    // Igual que arriba: el borrador es una comodidad, no un dato que se pueda perder.
  }
}

/**
 * Modo "diseñar por especificaciones". La persona escribe requisitos uno por
 * uno; mientras escribe, el sistema reconoce de qué va el proyecto y ofrece
 * cómo completar la frase. Al decir "listo", el Analista agrupa los
 * requisitos en módulos, mide qué falta y pregunta (como mucho 5 preguntas,
 * cada una con una opción recomendada) o recomienda requisitos para
 * autocompletar. El resultado es un pedido para la misma fábrica de siempre.
 */
export default function DisenadorSpecs({
  onEncargar,
}: {
  onEncargar: (pedido: string) => Promise<void>;
}) {
  const [fase, setFase] = useState<Fase>("escribir");
  const [requisitos, setRequisitos] = useState<string[]>([]);
  const [respuestas, setRespuestas] = useState<Record<string, RespuestaRequisito>>({});
  const [borrador, setBorrador] = useState("");
  const [vivo, setVivo] = useState<SugerenciasRequisitos | null>(null);
  const [analisis, setAnalisis] = useState<AnalisisRequisitos | null>(null);
  // Los módulos del análisis apuntan a posiciones de la lista: si la lista
  // cambió después de analizar, ya no sirven y el servidor reagrupa.
  const [analizadoCon, setAnalizadoCon] = useState<string[] | null>(null);
  const [pedido, setPedido] = useState("");
  const [ocupado, setOcupado] = useState<null | "analizando" | "componiendo" | "encargando">(null);
  const [error, setError] = useState<string | null>(null);
  const [cargado, setCargado] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const b = leerBorrador();
    setRequisitos(b.requisitos);
    setRespuestas(b.respuestas);
    setCargado(true);
  }, []);

  useEffect(() => {
    if (cargado) guardarBorrador({ requisitos, respuestas });
  }, [requisitos, respuestas, cargado]);

  // Sugerencias en vivo: deterministas y gratis, con una pausa corta del teclado.
  useEffect(() => {
    if (!cargado) return;
    const t = setTimeout(() => {
      sugerirRequisitos(requisitos, borrador)
        .then(setVivo)
        .catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [requisitos, borrador, cargado]);

  const desactualizado =
    analisis !== null && JSON.stringify(analizadoCon) !== JSON.stringify(requisitos);

  function agregar(texto: string) {
    const limpio = texto.trim().replace(/\s+/g, " ");
    if (!limpio) return;
    if (requisitos.some((r) => r.toLowerCase() === limpio.toLowerCase())) {
      setBorrador("");
      return;
    }
    setRequisitos((prev) => [...prev, limpio]);
    setBorrador("");
    entrada.current?.focus();
  }

  function quitar(i: number) {
    setRequisitos((prev) => prev.filter((_, j) => j !== i));
  }

  function editar(i: number, texto: string) {
    setRequisitos((prev) => prev.map((r, j) => (j === i ? texto : r)));
  }

  function vaciar() {
    setRequisitos([]);
    setRespuestas({});
    setAnalisis(null);
    setPedido("");
    setFase("escribir");
  }

  async function analizar() {
    const limpios = requisitos.map((r) => r.trim()).filter(Boolean);
    if (!limpios.length) return;
    setOcupado("analizando");
    setError(null);
    try {
      const r = await analizarRequisitos(limpios, Object.values(respuestas));
      setRequisitos(limpios);
      setAnalisis(r);
      setAnalizadoCon(limpios);
      setFase("revisar");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo analizar");
    } finally {
      setOcupado(null);
    }
  }

  function responder(p: PreguntaRequisitos, respuesta: string) {
    setRespuestas((prev) => ({
      ...prev,
      [p.id]: { categoria: p.categoria, pregunta: p.texto, respuesta },
    }));
  }

  function aceptarRecomendadas() {
    if (!analisis) return;
    for (const p of analisis.preguntas) {
      if (!respuestas[p.id]) responder(p, p.opciones[p.recomendada]);
    }
  }

  const preguntasAbiertas = useMemo(
    () => (analisis?.preguntas ?? []).filter((p) => !respuestas[p.id]),
    [analisis, respuestas],
  );
  const recomendacionesNuevas = useMemo(
    () =>
      (analisis?.recomendaciones ?? []).filter(
        (r) => !requisitos.some((x) => x.toLowerCase() === r.texto.toLowerCase()),
      ),
    [analisis, requisitos],
  );

  async function generar() {
    if (!analisis) return;
    // Lo que quedó sin responder va con la opción recomendada, y se dice.
    const finales = { ...respuestas };
    for (const p of analisis.preguntas) {
      if (!finales[p.id]) {
        finales[p.id] = {
          categoria: p.categoria,
          pregunta: p.texto,
          respuesta: p.opciones[p.recomendada],
        };
      }
    }
    setRespuestas(finales);
    setOcupado("componiendo");
    setError(null);
    try {
      const r = await componerPedido(
        requisitos,
        Object.values(finales),
        desactualizado ? null : analisis.modulos,
        analisis.intencion.resumen,
      );
      setPedido(r.pedido);
      setFase("pedido");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo armar el pedido");
    } finally {
      setOcupado(null);
    }
  }

  async function encargar() {
    setOcupado("encargando");
    setError(null);
    try {
      await onEncargar(pedido);
      vaciar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo encargar");
    } finally {
      setOcupado(null);
    }
  }

  const intencion = analisis?.intencion ?? vivo?.intencion;
  const indicePaso = PASOS.findIndex((p) => p.fase === fase);
  const modulosPedido = pedido.split("\n").filter((l) => l.startsWith("- ")).length;

  return (
    <section className="disenador" aria-label="Diseñar por especificaciones">
      <ol className="pasos-disenador">
        {PASOS.map((p, i) => (
          <li key={p.fase} className={i === indicePaso ? "actual" : i < indicePaso ? "hecho" : ""}>
            <span className="numero-paso">{i < indicePaso ? <Check size={14} /> : i + 1}</span>
            {p.etiqueta}
          </li>
        ))}
      </ol>

      {intencion && (intencion.dominio || requisitos.length > 0) && (
        <div className="intencion-viva" aria-live="polite">
          <Sparkles size={18} aria-hidden />
          <div>
            <strong>{intencion.dominio ? intencion.nombre : "Tipo de proyecto aún no claro"}</strong>
            <span>{intencion.resumen}</span>
          </div>
          {intencion.dominio && (
            <span
              className="medidor-confianza"
              title={`Confianza: ${Math.round(intencion.confianza * 100)}%`}
            >
              <i style={{ width: `${Math.round(intencion.confianza * 100)}%` }} />
            </span>
          )}
        </div>
      )}

      {fase === "escribir" && (
        <>
          <form
            className="fila-requisito"
            onSubmit={(e) => {
              e.preventDefault();
              agregar(borrador);
            }}
          >
            <input
              ref={entrada}
              value={borrador}
              onChange={(e) => setBorrador(e.target.value)}
              onKeyDown={(e) => {
                // Tab acepta el primer autocompletado, como en un editor.
                if (e.key === "Tab" && !e.shiftKey && vivo?.autocompletado[0] && borrador.trim()) {
                  e.preventDefault();
                  setBorrador(vivo.autocompletado[0]);
                }
              }}
              placeholder="Escribe un requisito… p. ej. Registrar clientes con nombre y email"
              aria-label="Nuevo requisito"
              maxLength={500}
            />
            <button type="submit" disabled={!borrador.trim()}>
              <Plus size={16} aria-hidden /> Agregar
            </button>
          </form>

          {borrador.trim() && vivo && vivo.autocompletado.length > 0 && (
            <div className="autocompletar">
              <span className="etiqueta-subseccion">
                <Wand2 size={12} aria-hidden /> Completar la idea {" · "}
                <kbd>Tab</kbd> acepta la primera
              </span>
              {vivo.autocompletado.map((s) => (
                <button key={s} type="button" className="chip-sugerencia" onClick={() => agregar(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}

          {requisitos.length === 0 ? (
            <p className="apagado vacio-disenador">
              Escribe una funcionalidad por línea, en tus palabras. No hace falta que esté completo:
              cuando digas que está listo, la fábrica agrupa, detecta lo que falta y te pregunta o te
              recomienda cómo completarlo.
            </p>
          ) : (
            <ol className="lista-requisitos">
              {requisitos.map((r, i) => (
                <li key={i}>
                  <span className="mono numero-requisito">{i + 1}</span>
                  <input
                    value={r}
                    onChange={(e) => editar(i, e.target.value)}
                    aria-label={`Requisito ${i + 1}`}
                    maxLength={500}
                  />
                  <button
                    type="button"
                    className="boton-icono"
                    onClick={() => quitar(i)}
                    aria-label={`Quitar el requisito ${i + 1}`}
                  >
                    <X size={16} />
                  </button>
                </li>
              ))}
            </ol>
          )}

          {vivo && vivo.sugerencias.length > 0 && (
            <div className="sugerencias-dominio">
              <span className="etiqueta-subseccion">
                <Lightbulb size={12} aria-hidden /> Suele hacer falta en{" "}
                {vivo.intencion.nombre.toLowerCase()}
              </span>
              <div className="fila-pastillas">
                {vivo.sugerencias.map((s) => (
                  <button key={s} type="button" className="chip-sugerencia" onClick={() => agregar(s)}>
                    <Plus size={14} aria-hidden /> {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="pie-disenador">
            <button
              type="button"
              className="primario"
              disabled={!requisitos.some((r) => r.trim()) || ocupado !== null}
              onClick={analizar}
            >
              {ocupado === "analizando" ? "Analizando…" : "Listo, analizar especificaciones"}
            </button>
            {requisitos.length > 0 && (
              <button type="button" onClick={vaciar}>
                Empezar de cero
              </button>
            )}
            <span className="apagado">
              {requisitos.length} requisito{requisitos.length === 1 ? "" : "s"} · el borrador se
              guarda solo en este navegador
            </span>
          </div>
        </>
      )}

      {fase === "revisar" && analisis && (
        <>
          <div className="cobertura-requisitos" aria-label="Cobertura de la especificación">
            {Object.entries(analisis.cobertura).map(([cat, estado]) => (
              <span key={cat} className={`chip-cobertura ${estado}`}>
                {CATEGORIAS_REQUISITOS[cat] ?? cat}: {ETIQUETA_COBERTURA[estado]}
              </span>
            ))}
            <span className="apagado origen-analisis">
              {analisis.origen === "cerebro"
                ? `analizado con ${analisis.modelo || "el cerebro"}`
                : "análisis automático"}
            </span>
          </div>

          <h3 className="subtitulo-disenador">Así lo agrupé</h3>
          {desactualizado ? (
            <p className="apagado">
              Cambiaste la lista después de analizar: los módulos se recalculan al generar o al
              volver a analizar.
            </p>
          ) : (
            <div className="rejilla-modulos">
              {analisis.modulos.map((m) => (
                <article key={m.nombre} className="tarjeta-modulo">
                  <strong>{m.nombre}</strong>
                  <ul>
                    {m.requisitos.map((i) => (
                      <li key={i}>{requisitos[i]}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          )}

          {analisis.preguntas.length > 0 && (
            <>
              <div className="titulo-con-enlace">
                <h3 className="subtitulo-disenador">
                  Para completar la especificación
                  {preguntasAbiertas.length > 0 && (
                    <span className="contador-preguntas">{preguntasAbiertas.length} sin responder</span>
                  )}
                </h3>
                {preguntasAbiertas.length > 0 && (
                  <button type="button" onClick={aceptarRecomendadas}>
                    <Check size={14} aria-hidden /> Aceptar las recomendadas
                  </button>
                )}
              </div>
              {analisis.preguntas.map((p) => (
                <PreguntaCard
                  key={p.id}
                  pregunta={p}
                  elegida={respuestas[p.id]?.respuesta}
                  onElegir={(r) => responder(p, r)}
                />
              ))}
            </>
          )}

          {recomendacionesNuevas.length > 0 && (
            <>
              <div className="titulo-con-enlace">
                <h3 className="subtitulo-disenador">Te recomiendo agregar</h3>
                <button
                  type="button"
                  onClick={() =>
                    setRequisitos((prev) => [...prev, ...recomendacionesNuevas.map((r) => r.texto)])
                  }
                >
                  <Wand2 size={14} aria-hidden /> Autocompletar: agregar todas
                </button>
              </div>
              <ul className="lista-recomendaciones">
                {recomendacionesNuevas.map((r) => (
                  <li key={r.texto}>
                    <div>
                      <span className="etiqueta-subseccion">
                        {CATEGORIAS_REQUISITOS[r.categoria] ?? r.categoria}
                      </span>
                      <p>{r.texto}</p>
                      {r.porque && <small className="apagado">{r.porque}</small>}
                    </div>
                    <button type="button" onClick={() => setRequisitos((prev) => [...prev, r.texto])}>
                      <Plus size={14} aria-hidden /> Agregar
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="pie-disenador">
            <button type="button" onClick={() => setFase("escribir")}>
              <ArrowLeft size={14} aria-hidden /> Seguir editando
            </button>
            {desactualizado && (
              <button type="button" onClick={analizar} disabled={ocupado !== null}>
                <RefreshCw size={14} aria-hidden />{" "}
                {ocupado === "analizando" ? "Analizando…" : "Volver a analizar"}
              </button>
            )}
            <button type="button" className="primario" onClick={generar} disabled={ocupado !== null}>
              {ocupado === "componiendo" ? "Armando…" : "Generar la especificación final"}
            </button>
            {preguntasAbiertas.length > 0 && (
              <span className="apagado">
                Lo que quede sin responder va con la opción recomendada.
              </span>
            )}
          </div>
        </>
      )}

      {fase === "pedido" && (
        <>
          <p className="apagado">
            Este es el pedido que recibirá la fábrica. Cada módulo se convierte en una
            especificación ({modulosPedido} en total) y las que no dependen entre sí se construyen en
            paralelo. Puedes editarlo antes de encargar.
          </p>
          <textarea
            className="pedido-final mono"
            rows={Math.min(18, pedido.split("\n").length + 2)}
            value={pedido}
            onChange={(e) => setPedido(e.target.value)}
            maxLength={8000}
            aria-label="Pedido final"
          />
          <div className="pie-disenador">
            <button type="button" onClick={() => setFase("revisar")}>
              <ArrowLeft size={14} aria-hidden /> Volver
            </button>
            <button
              type="button"
              className="primario"
              onClick={encargar}
              disabled={ocupado !== null || pedido.trim().length < 3}
            >
              {ocupado === "encargando" ? "Encargando…" : "Encargar a la fábrica"}
            </button>
          </div>
        </>
      )}

      {error && <p className="error">{error}</p>}
    </section>
  );
}

function PreguntaCard({
  pregunta,
  elegida,
  onElegir,
}: {
  pregunta: PreguntaRequisitos;
  elegida: string | undefined;
  onElegir: (respuesta: string) => void;
}) {
  const [libre, setLibre] = useState("");
  const propia = elegida !== undefined && !pregunta.opciones.includes(elegida);
  return (
    <article className={`tarjeta-pregunta-spec ${elegida ? "respondida" : ""}`}>
      <span className="etiqueta-subseccion">
        {CATEGORIAS_REQUISITOS[pregunta.categoria] ?? pregunta.categoria}
      </span>
      <p className="texto-pregunta">{pregunta.texto}</p>
      {pregunta.porque && <small className="apagado">Por qué importa: {pregunta.porque}</small>}
      <div className="opciones-pregunta" role="radiogroup" aria-label={pregunta.texto}>
        {pregunta.opciones.map((o, i) => (
          <button
            key={o}
            type="button"
            role="radio"
            aria-checked={elegida === o}
            className={`opcion ${elegida === o ? "elegida" : ""}`}
            onClick={() => onElegir(o)}
          >
            {elegida === o && <Check size={14} aria-hidden />} {o}
            {i === pregunta.recomendada && <span className="insignia-recomendada">Recomendada</span>}
          </button>
        ))}
      </div>
      <form
        className="fila-alta"
        onSubmit={(e) => {
          e.preventDefault();
          if (libre.trim()) onElegir(libre.trim());
          setLibre("");
        }}
      >
        <input
          value={libre}
          onChange={(e) => setLibre(e.target.value)}
          placeholder={propia ? `Tu respuesta: ${elegida}` : "…o escribe tu propia respuesta"}
          aria-label="Respuesta propia"
          maxLength={400}
        />
        <button type="submit" disabled={!libre.trim()}>
          Usar
        </button>
      </form>
    </article>
  );
}
