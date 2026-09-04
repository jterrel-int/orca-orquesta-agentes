import type { EstadoAgente } from "@/lib/types";

const ETIQUETA: Record<EstadoAgente, string> = {
  pending: "en espera",
  running: "ejecutando",
  done: "listo",
  error: "error",
};

export default function EstadoPunto({ status }: { status: EstadoAgente }) {
  return (
    <span className={`estado ${status}`}>
      <span className="punto" aria-hidden />
      {ETIQUETA[status]}
    </span>
  );
}
