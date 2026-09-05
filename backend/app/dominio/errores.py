"""Excepciones de dominio. El dominio no conoce HTTPException; la capa de API
las traduce a códigos HTTP en el borde.
"""

from __future__ import annotations


class ErrorDominio(Exception):
    """Base de las excepciones de dominio."""


class ItemNoEncontrado(ErrorDominio):
    def __init__(self, item_id: int) -> None:
        super().__init__(f"Item {item_id} no encontrado")
        self.item_id = item_id


class DespliegueFallido(ErrorDominio):
    """El Desplegador no pudo completar el despliegue."""


class CorridaEnCurso(ErrorDominio):
    """Ya hay una corrida de agentes en curso; no se puede lanzar otra."""


class OAuthFallido(ErrorDominio):
    """El intercambio OAuth con un proveedor externo no se completó."""


class CredencialInvalida(ErrorDominio):
    """La credencial provista no fue aceptada por el proveedor externo."""
