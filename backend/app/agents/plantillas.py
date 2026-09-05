"""Plantillas de código que los agentes escriben en disco.

Viven separadas de la lógica del agente para que el respaldo determinista y la
salida de un LLM se puedan comparar contra la misma referencia.
"""

ROUTER_ITEMS = '''"""Generado por BackendAgent — no editar a mano.

Router CRUD para la entidad Item. La aplicación lo monta en caliente al
terminar la corrida de agentes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..adaptadores.persistencia_sqlalchemy import RepositorioItemsSQLAlchemy, obtener_sesion
from ..api.items import ItemActualizar, ItemCrear, ItemLeer, item_a_leer
from ..dominio.errores import ItemNoEncontrado
from ..dominio.servicios import ServicioItems

router = APIRouter(prefix="/api/items", tags=["items (generado)"])


async def _servicio(sesion: AsyncSession = Depends(obtener_sesion)) -> ServicioItems:
    return ServicioItems(RepositorioItemsSQLAlchemy(sesion))


@router.get("", response_model=list[ItemLeer])
async def listar(servicio: ServicioItems = Depends(_servicio)) -> list[ItemLeer]:
    return [item_a_leer(i) for i in await servicio.listar()]


@router.post("", response_model=ItemLeer, status_code=status.HTTP_201_CREATED)
async def crear(datos: ItemCrear, servicio: ServicioItems = Depends(_servicio)) -> ItemLeer:
    return item_a_leer(await servicio.crear(datos.name))


@router.get("/{item_id}", response_model=ItemLeer)
async def obtener(item_id: int, servicio: ServicioItems = Depends(_servicio)) -> ItemLeer:
    try:
        return item_a_leer(await servicio.obtener(item_id))
    except ItemNoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{item_id}", response_model=ItemLeer)
async def actualizar(
    item_id: int, datos: ItemActualizar, servicio: ServicioItems = Depends(_servicio)
) -> ItemLeer:
    try:
        return item_a_leer(await servicio.actualizar(item_id, datos.name))
    except ItemNoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(item_id: int, servicio: ServicioItems = Depends(_servicio)) -> None:
    try:
        await servicio.eliminar(item_id)
    except ItemNoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
'''


LISTA_ITEMS_TSX = '''// Generado por FrontendAgent — no editar a mano.
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
'''
