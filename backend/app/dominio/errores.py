"""Excepciones de dominio. El dominio no conoce HTTPException; la capa de API
las traduce a códigos HTTP en el borde.
"""

from __future__ import annotations


class ErrorDominio(Exception):
    """Base de las excepciones de dominio."""


class DespliegueFallido(ErrorDominio):
    """El Desplegador no pudo completar el despliegue."""


class OAuthFallido(ErrorDominio):
    """El intercambio OAuth con un proveedor externo no se completó."""


class CredencialInvalida(ErrorDominio):
    """La credencial provista no fue aceptada por el proveedor externo."""


class DocumentoNoLegible(ErrorDominio):
    """El documento importado no tiene texto extraíble (formato no soportado,
    o un PDF/imagen escaneada sin capa de texto).
    """


class EncargoNoEncontrado(ErrorDominio):
    def __init__(self, encargo_id: str) -> None:
        super().__init__(f"Encargo {encargo_id} no encontrado")
        self.encargo_id = encargo_id


class AccionNoPermitida(ErrorDominio):
    """La acción humana pedida no corresponde al estado actual del encargo
    (responder una pregunta ya respondida, aprobar algo que no espera
    aprobación, reanudar algo que ya corre).
    """
