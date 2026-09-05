"use client";

import { useEffect, useState } from "react";
import { salud } from "@/lib/api";
import type { Salud } from "@/lib/types";

/**
 * Qué cerebro está activo, si el deploy real está encendido, y qué falta si
 * algo falta. Un solo GET al montar — esto no cambia mientras el proceso
 * corre, así que no hace falta sondear como sí hace el WebSocket.
 */
export default function EstadoSistema() {
  const [estado, setEstado] = useState<Salud | null>(null);

  useEffect(() => {
    let vivo = true;
    salud()
      .then((s) => {
        if (vivo) setEstado(s);
      })
      .catch(() => {
        // Si /api/health no responde, la pastilla de WS ya lo dice.
      });
    return () => {
      vivo = false;
    };
  }, []);

  if (!estado) return null;

  return (
    <div className="estado-sistema">
      <div className="fila-pastillas">
        <span className="pastilla">
          Cerebro: {estado.brain === "anthropic" ? "Anthropic" : "guionado"}
        </span>
        <span className={`pastilla ${estado.deploy_enabled ? "activa" : ""}`}>
          Deploy: {estado.deploy_enabled ? "activo" : "apagado"}
        </span>
      </div>

      {estado.advertencias.length > 0 && (
        <div className="aviso-config" role="status">
          <strong>Configuración incompleta</strong>
          <ul>
            {estado.advertencias.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
