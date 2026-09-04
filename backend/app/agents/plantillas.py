"""Plantillas de código que los agentes escriben en disco.

Viven separadas de la lógica del agente para que el respaldo determinista y la
salida de un LLM se puedan comparar contra la misma referencia.
"""

ROUTER_ITEMS = '''"""Generado por BackendAgent — no editar a mano.

Router CRUD para la entidad Item. La aplicación lo monta en caliente al
terminar la corrida de agentes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import obtener_sesion
from ..models.item import Item, ItemActualizar, ItemCrear, ItemLeer

router = APIRouter(prefix="/api/items", tags=["items (generado)"])


@router.get("", response_model=list[ItemLeer])
async def listar(sesion: AsyncSession = Depends(obtener_sesion)) -> list[Item]:
    resultado = await sesion.execute(select(Item).order_by(Item.id.desc()))
    return list(resultado.scalars().all())


@router.post("", response_model=ItemLeer, status_code=status.HTTP_201_CREATED)
async def crear(datos: ItemCrear, sesion: AsyncSession = Depends(obtener_sesion)) -> Item:
    item = Item(name=datos.name)
    sesion.add(item)
    await sesion.commit()
    await sesion.refresh(item)
    return item


@router.get("/{item_id}", response_model=ItemLeer)
async def obtener(item_id: int, sesion: AsyncSession = Depends(obtener_sesion)) -> Item:
    item = await sesion.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    return item


@router.put("/{item_id}", response_model=ItemLeer)
async def actualizar(
    item_id: int, datos: ItemActualizar, sesion: AsyncSession = Depends(obtener_sesion)
) -> Item:
    item = await sesion.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    item.name = datos.name
    await sesion.commit()
    await sesion.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(item_id: int, sesion: AsyncSession = Depends(obtener_sesion)) -> None:
    item = await sesion.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    await sesion.delete(item)
    await sesion.commit()
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
