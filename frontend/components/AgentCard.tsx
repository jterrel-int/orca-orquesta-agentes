import EstadoPunto from "./EstadoPunto";
import type { EstadoAgente } from "@/lib/types";

interface Props {
  agente: string;
  status: EstadoAgente;
  ultimo: string;
  duracion?: number | null;
}

export default function AgentCard({ agente, status, ultimo, duracion }: Props) {
  return (
    <article className="tarjeta" style={{ ["--matiz" as string]: `var(--${agente})` }}>
      <div className="nombre">{agente}</div>
      <div className="ultimo">{ultimo || "Sin actividad todavía"}</div>
      <div className="pie">
        <EstadoPunto status={status} />
        {duracion != null && <span className="mono">{duracion.toFixed(1)}s</span>}
      </div>
    </article>
  );
}
