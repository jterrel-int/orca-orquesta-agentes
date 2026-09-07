"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import EstadoSistema from "@/components/EstadoSistema";
import ListaProyectos from "@/components/ListaProyectos";
import { casosDeUso, estadoCorrida } from "@/lib/api";
import { useEventos } from "@/lib/ws";
import type { CasoDeUso, ResumenCorrida } from "@/lib/types";

export default function Panel() {
  const { eventos, conexion } = useEventos();
  const [casos, setCasos] = useState<CasoDeUso[]>([]);
  const [resumen, setResumen] = useState<ResumenCorrida | null>(null);

  useEffect(() => {
    casosDeUso()
      .then(setCasos)
      .catch(() => {
        // Si no responde, la pastilla de WS/salud ya avisa que algo anda mal.
      });
  }, []);

  // Se reconsulta con cada evento nuevo: durante una corrida llegan seguido,
  // así que el estado de la corrida (incluido su caso_de_uso) se mantiene al día.
  useEffect(() => {
    estadoCorrida()
      .then(setResumen)
      .catch(() => {});
  }, [eventos.length]);

  const corriendo = useMemo(() => {
    const ultimoOrq = [...eventos].reverse().find((e) => e.agent === "orchestrator");
    return ultimoOrq?.status === "running" || resumen?.status === "running";
  }, [eventos, resumen]);

  const proyectoActivo = casos.find((c) => (resumen?.caso_de_uso ?? "items") === c.id);

  return (
    <>
      <header className="cabecera">
        <h1>Proyectos</h1>
        <span className="sub">casos de prueba para ver a los agentes trabajar</span>
        <div className="derecha">
          <span
            className={`pastilla ${conexion === "conectado" ? "viva" : conexion === "desconectado" ? "muerta" : ""}`}
          >
            {conexion === "conectado" ? "WS conectado" : conexion === "conectando" ? "conectando…" : "WS caído"}
          </span>
        </div>
      </header>

      <main className="contenido">
        <EstadoSistema />

        {corriendo && proyectoActivo && (
          <div className="banner-corriendo">
            <span aria-hidden>{proyectoActivo.icono}</span>
            <span>
              <strong>{proyectoActivo.nombre}</strong> se está ejecutando ahora.
            </span>
            <Link href={`/proyectos/${proyectoActivo.id}`}>Ver progreso →</Link>
          </div>
        )}

        <ListaProyectos proyectos={casos} resumen={resumen} />
      </main>
    </>
  );
}
