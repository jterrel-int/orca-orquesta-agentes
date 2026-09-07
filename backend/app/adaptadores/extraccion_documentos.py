"""Extrae texto plano de specs subidas (.txt, .md, .pdf, .docx).

Así el dominio (`ServicioBacklog.generar_desde_especificacion`) trabaja
siempre con texto, nunca con bytes ni formatos de archivo — el mismo
principio que `backlog_markdown.py` aplica para docs/BACKLOG.md.
"""

from __future__ import annotations

import io

from docx import Document
from pypdf import PdfReader

from ..dominio.errores import DocumentoNoLegible

# Menos que esto y asumimos que no hay texto real que extraer (por ejemplo,
# un PDF que es solo páginas escaneadas sin capa de texto).
_MIN_CARACTERES = 30

_EXTENSIONES_SOPORTADAS = ("txt", "md", "pdf", "docx")


def extraer_texto(nombre_archivo: str, contenido: bytes) -> str:
    extension = nombre_archivo.rsplit(".", 1)[-1].lower() if "." in nombre_archivo else ""

    if extension not in _EXTENSIONES_SOPORTADAS:
        raise DocumentoNoLegible(
            f"Formato no soportado: .{extension or '?'}. Usá .txt, .md, .pdf o .docx."
        )

    if extension in ("txt", "md"):
        texto = _decodificar(contenido)
    elif extension == "pdf":
        texto = _extraer_pdf(contenido)
    else:
        texto = _extraer_docx(contenido)

    texto = texto.strip()
    if len(texto) < _MIN_CARACTERES:
        raise DocumentoNoLegible(
            "El documento no tiene texto legible que se pueda extraer — ¿es una imagen "
            "escaneada o un PDF sin capa de texto? Subí una versión con texto real, o "
            "pegá el texto directamente."
        )
    return texto


def _decodificar(contenido: bytes) -> str:
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("latin-1", errors="ignore")


def _extraer_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)


def _extraer_docx(contenido: bytes) -> str:
    documento = Document(io.BytesIO(contenido))
    return "\n".join(parrafo.text for parrafo in documento.paragraphs)
