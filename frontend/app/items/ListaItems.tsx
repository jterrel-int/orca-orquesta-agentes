// Generado por FrontendAgent — no editar a mano.
"use client";

import { useEffect, useState } from "react";
import { listarItems, crearItem, eliminarItem, type Item } from "@/lib/api";

export default function ListaItems() {
  const [items, setItems] = useState<Item[]>([]);
  const [nombre, setNombre] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refrescar() {
    try {
      setItems(await listarItems());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    refrescar();
  }, []);

  async function agregar() {
    const limpio = nombre.trim();
    if (!limpio) return;
    await crearItem(limpio);
    setNombre("");
    refrescar();
  }

  if (cargando) return <p className="apagado">Cargando items…</p>;

  return (
    <div className="lista-items">
      <div className="fila-alta">
        <input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && agregar()}
          placeholder="Nombre del item"
          aria-label="Nombre del item"
        />
        <button onClick={agregar} disabled={!nombre.trim()}>
          Agregar
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {items.length === 0 ? (
        <p className="apagado">
          No hay items todavía. El backend responde, la tabla está vacía.
        </p>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th style={{ width: "4rem" }}>ID</th>
              <th>Nombre</th>
              <th style={{ width: "3rem" }} />
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id}>
                <td className="mono">{it.id}</td>
                <td>{it.name}</td>
                <td>
                  <button
                    className="icono"
                    onClick={() => eliminarItem(it.id).then(refrescar)}
                    aria-label={`Eliminar ${it.name}`}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
