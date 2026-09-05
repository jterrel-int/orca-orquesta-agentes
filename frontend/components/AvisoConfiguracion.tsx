"use client";

import { useEffect, useState } from "react";
import { salud } from "@/lib/api";

/**
 * Config que arrancó igual pero probablemente no es la esperada (una clave
 * que falta, el CLI de Vercel ausente). Un solo GET al montar: esto no
 * cambia mientras el proceso corre, así que no hace falta sondear.
 */
export default function AvisoConfiguracion() {
  const [advertencias, setAdvertencias] = useState<string[]>([]);

  useEffect(() => {
    let vivo = true;
    salud()
      .then((s) => {
        if (vivo) setAdvertencias(s.advertencias);
      })
      .catch(() => {
        // Si /api/health no responde, la pastilla de WS ya lo dice.
      });
    return () => {
      vivo = false;
    };
  }, []);

  if (advertencias.length === 0) return null;

  return (
    <div className="aviso-config" role="status">
      <strong>Configuración incompleta</strong>
      <ul>
        {advertencias.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
    </div>
  );
}
