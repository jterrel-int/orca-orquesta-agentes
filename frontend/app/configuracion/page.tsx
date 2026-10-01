"use client";

import { useEffect, useState } from "react";
import ConexionAnthropic from "@/components/ConexionAnthropic";
import ConexionRender from "@/components/ConexionRender";
import ConexionVercel from "@/components/ConexionVercel";
import { salud } from "@/lib/api";
import type { Salud } from "@/lib/types";

export default function PaginaConfiguracion() {
  const [estado, setEstado] = useState<Salud | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    salud()
      .then((s) => {
        if (vivo) setEstado(s);
      })
      .catch((e: unknown) => {
        if (vivo) setError(e instanceof Error ? e.message : "No se pudo cargar /api/health");
      });
    return () => {
      vivo = false;
    };
  }, []);

  return (
    <>
      <header className="cabecera">
        <h1>Configuración</h1>
        <span className="sub">variables de entorno activas en este proceso</span>
      </header>

      <main className="contenido">
        <p className="apagado" style={{ maxWidth: "60ch", marginBottom: "1.25rem" }}>
          Esto se lee de <code>backend/.env</code> al arrancar el proceso — cambiarlo acá no hace
          nada. Para que tome efecto hay que editar el archivo y reiniciar el backend.
        </p>

        {error && <p className="error">{error}</p>}
        {!estado && !error && <p className="apagado">Cargando…</p>}

        {estado && (
          <>
            <dl className="lista-config">
              <div>
                <dt>Cerebro activo</dt>
                <dd>
                  {estado.cerebro_activo === "anthropic" ? (
                    <>
                      Anthropic — modelo <span className="mono">{estado.cerebro_modelo}</span> (
                      {estado.cerebro_fuente})
                    </>
                  ) : estado.cerebro_activo === "claude-cli" ? (
                    <>
                      Claude Code CLI local (<span className="mono">{estado.cerebro_fuente}</span>
                      ) — usa la sesión de esta máquina, no una API key. Solo funciona acá, no en
                      un backend desplegado.
                      <br />
                      Cuenta que va a gastar las corridas:{" "}
                      {estado.cerebro_cuenta ? (
                        <span className="mono">{estado.cerebro_cuenta}</span>
                      ) : (
                        "no se pudo determinar (¿claude auth status funciona en esta terminal?)"
                      )}
                    </>
                  ) : (
                    "Guionado (determinista, sin IA real — conectá Anthropic abajo)"
                  )}
                </dd>
              </div>
              <div>
                <dt>Despliegue real</dt>
                <dd>
                  {estado.deploy_enabled
                    ? "Activo — vercel --prod se ejecuta de verdad"
                    : "Apagado (por defecto)"}
                </dd>
              </div>
              <div>
                <dt>Token de Vercel</dt>
                <dd>
                  {estado.vercel_token_configurado
                    ? "Configurado"
                    : "No configurado (usa la sesión local del CLI si hace falta)"}
                </dd>
              </div>
              <div>
                <dt>Conexiones WebSocket activas</dt>
                <dd>{estado.conexiones_ws}</dd>
              </div>
              <div>
                <dt>Orígenes permitidos (CORS)</dt>
                <dd>{estado.origenes_permitidos.join(", ") || "ninguno"}</dd>
              </div>
            </dl>

            {estado.advertencias.length > 0 && (
              <div className="aviso-config" role="status" style={{ marginTop: "1.25rem" }}>
                <strong>Configuración incompleta</strong>
                <ul>
                  {estado.advertencias.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        <h2 style={{ fontSize: "0.95rem", margin: "1.75rem 0 0.75rem" }}>Conexiones</h2>
        <div className="rejilla-conexiones">
          <ConexionAnthropic />
          <ConexionVercel />
          <ConexionRender />
        </div>
      </main>
    </>
  );
}
