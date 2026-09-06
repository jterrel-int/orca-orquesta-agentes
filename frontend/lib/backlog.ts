/**
 * Parsing del campo `cuerpo` de una `TareaBacklog`. El backend lo entrega como
 * un bloque de markdown plano con subsecciones tipo `**Archivos:** ...`,
 * `**Verificación:** ...`, `**Depende de:** ...` (mismo formato que
 * `docs/BACKLOG.md`). Esta función lo separa en bloques para poder
 * renderizarlos por separado, sin depender de ninguna librería de markdown.
 *
 * Reusable desde cualquier otra pantalla que necesite el mismo patrón (por
 * ejemplo, el rediseño del panel en FE-06).
 */

export interface SeccionTarea {
  /** `null` cuando es el texto introductorio, antes de la primera subsección. */
  titulo: string | null;
  texto: string;
}

const ENCABEZADO_SUBSECCION = /\*\*([^*]+):\*\*/g;

export function partirCuerpoTarea(cuerpo: string): SeccionTarea[] {
  const secciones: SeccionTarea[] = [];
  let indiceAnterior = 0;
  let tituloActual: string | null = null;

  ENCABEZADO_SUBSECCION.lastIndex = 0;
  let coincidencia: RegExpExecArray | null;
  while ((coincidencia = ENCABEZADO_SUBSECCION.exec(cuerpo)) !== null) {
    const texto = cuerpo.slice(indiceAnterior, coincidencia.index).trim();
    if (texto) secciones.push({ titulo: tituloActual, texto });
    tituloActual = coincidencia[1].trim();
    indiceAnterior = ENCABEZADO_SUBSECCION.lastIndex;
  }

  const restante = cuerpo.slice(indiceAnterior).trim();
  if (restante || tituloActual) secciones.push({ titulo: tituloActual, texto: restante });

  // Formato inesperado (sin ninguna subsección reconocible): mostrar tal cual.
  return secciones.length > 0 ? secciones : [{ titulo: null, texto: cuerpo }];
}
