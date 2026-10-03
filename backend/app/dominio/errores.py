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


class EtapaVencida(ErrorDominio):
    """Una etapa superó el tope de tiempo de la política: el cerebro o el
    subproceso quedó colgado. El Líder la cierra en vez de esperar para siempre.
    """

    def __init__(self, etapa: str, segundos: float) -> None:
        super().__init__(f"La etapa «{etapa}» superó el tope de {segundos:.0f} s")
        self.etapa = etapa
        self.segundos = segundos


class AccionNoPermitida(ErrorDominio):
    """La acción humana pedida no corresponde al estado actual del encargo
    (responder una pregunta ya respondida, aprobar algo que no espera
    aprobación, reanudar algo que ya corre).
    """
