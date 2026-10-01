"use client";

import { useCallback, useEffect, useState } from "react";
import { usoAnthropic } from "@/lib/api";

const CLAVE_UMBRAL = "orquesta:uso-anthropic:ultimo-umbral";
const CLAVE_LIMITE = "orquesta:uso-anthropic:limite-visto";
const INTERVALO_MS = 15_000;

interface Toast {
  id: number;
  texto: string;
}

let contadorId = 0;

/**
 * Avisa por toast cada vez que el uso de tokens de Anthropic (contra el
 * límite que el usuario definió en Configuración) cruza un nuevo múltiplo de
 * 10%. Vive en el layout para verlo desde cualquier pantalla, no solo
 * Configuración, ya que el gasto se acumula durante las corridas de agentes.
 *
 * El umbral ya avisado se guarda en localStorage — no en el backend — porque
 * es una preferencia de "ya me enteré" de este navegador, no un dato del
 * dominio.
 */
export default function ToastUsoAnthropic() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const agregarToast = useCallback((texto: string) => {
    const id = ++contadorId;
    setToasts((actuales) => [...actuales, { id, texto }]);
    setTimeout(() => {
      setToasts((actuales) => actuales.filter((t) => t.id !== id));
    }, 8000);
  }, []);

  useEffect(() => {
    let vivo = true;

    async function chequear() {
      try {
        const uso = await usoAnthropic();
        if (!vivo || !uso || uso.limite_tokens <= 0) return;

        let ultimoUmbral = Number(localStorage.getItem(CLAVE_UMBRAL) ?? "0");
        const limiteVisto = Number(localStorage.getItem(CLAVE_LIMITE) ?? "0");

        // Si el límite cambió, el conteo de umbrales avisados arranca de nuevo.
        if (limiteVisto !== uso.limite_tokens) {
          ultimoUmbral = 0;
          localStorage.setItem(CLAVE_LIMITE, String(uso.limite_tokens));
        }

        const umbralActual = Math.min(100, Math.floor(uso.porcentaje / 10) * 10);
        if (umbralActual > ultimoUmbral) {
          for (let u = ultimoUmbral + 10; u <= umbralActual; u += 10) {
            const usados = uso.tokens_usados.toLocaleString("es");
            const limite = uso.limite_tokens.toLocaleString("es");
            agregarToast(
              u >= 100
                ? `Llegaste al 100% de tu límite de tokens de Anthropic (${usados} / ${limite}).`
                : `Vas ${u}% de tu límite de tokens de Anthropic (${usados} / ${limite}).`
            );
          }
          localStorage.setItem(CLAVE_UMBRAL, String(umbralActual));
        }
      } catch {
        // Sin backend disponible por un momento: no hay nada que avisar.
      }
    }

    chequear();
    const id = setInterval(chequear, INTERVALO_MS);
    return () => {
      vivo = false;
      clearInterval(id);
    };
  }, [agregarToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-contenedor" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className="toast">
          {t.texto}
        </div>
      ))}
    </div>
  );
}
