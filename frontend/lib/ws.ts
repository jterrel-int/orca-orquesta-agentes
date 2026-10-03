"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API, TOKEN } from "./api";
import type { EventoAgente } from "./types";

export type EstadoConexion = "conectando" | "conectado" | "desconectado";

/**
 * http(s) -> ws(s). Con el backend en Render (https) y el frontend en Vercel,
 * esto tiene que dar wss:// o el navegador rechaza la conexión por mixed content.
 */
export function urlWebSocket(apiUrl: string, token = ""): string {
  const base = apiUrl.replace(/^http/, "ws") + "/ws";
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

/**
 * Conexión al canal de eventos con reconexión y retroceso exponencial.
 *
 * El backend reenvía su historial al conectar, así que una pestaña abierta a
 * mitad de una corrida no aparece vacía. Por eso se reemplaza el arreglo en
 * vez de acumularlo cuando llega un evento de inicio de corrida.
 */
export function useEventos(maxEventos = 300) {
  const [eventos, setEventos] = useState<EventoAgente[]>([]);
  const [conexion, setConexion] = useState<EstadoConexion>("conectando");
  const wsRef = useRef<WebSocket | null>(null);
  const intentoRef = useRef(0);
  const vivoRef = useRef(true);

  const conectar = useCallback(() => {
    if (!vivoRef.current) return;

    const url = urlWebSocket(API, TOKEN);
    setConexion("conectando");

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      programarReintento();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      intentoRef.current = 0;
      setConexion("conectado");
    };

    ws.onmessage = (e) => {
      try {
        const evento = JSON.parse(e.data) as EventoAgente;
        setEventos((prev) => {
          const siguiente = [...prev, evento];
          return siguiente.length > maxEventos
            ? siguiente.slice(siguiente.length - maxEventos)
            : siguiente;
        });
      } catch {
        // Un mensaje mal formado no debe tumbar el stream.
      }
    };

    ws.onclose = () => {
      setConexion("desconectado");
      programarReintento();
    };

    ws.onerror = () => ws.close();

    function programarReintento() {
      if (!vivoRef.current) return;
      const espera = Math.min(1000 * 2 ** intentoRef.current, 15000);
      intentoRef.current += 1;
      setTimeout(() => vivoRef.current && conectar(), espera);
    }
  }, [maxEventos]);

  useEffect(() => {
    vivoRef.current = true;
    conectar();
    return () => {
      vivoRef.current = false;
      wsRef.current?.close();
    };
  }, [conectar]);

  const limpiar = useCallback(() => setEventos([]), []);

  return { eventos, conexion, limpiar };
}
