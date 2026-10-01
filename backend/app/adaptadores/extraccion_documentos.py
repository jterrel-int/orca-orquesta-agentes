"""Extrae texto plano de specs subidas (.txt, .md, .pdf, .docx).

La fábrica recibe siempre un pedido en texto; esto permite que ese pedido
venga de un documento (POST /api/fabrica/importar). Las viñetas de Word se
convierten en líneas "- …", que el Especificador usa para partir el pedido
en especificaciones.
"""

from __future__ import annotations

import io
import re

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


_PATRON_NIVEL_ENCABEZADO = re.compile(r"heading\s*(\d)", re.IGNORECASE)


def _extraer_docx(contenido: bytes) -> str:
    """Reconstruye encabezados markdown a partir de los estilos "Heading N"/
    "Title" de Word, y viñetas a partir de "List Bullet"/"List Number". Un
    .docx no usa "#" ni "-": la jerarquía vive en el estilo del párrafo, que
    se pierde si solo se junta `parrafo.text`.
    """
    documento = Document(io.BytesIO(contenido))
    lineas: list[str] = []
    for parrafo in documento.paragraphs:
        texto = parrafo.text.strip()
        if not texto:
            continue
        estilo = (parrafo.style.name if parrafo.style else "") or ""
        coincidencia = _PATRON_NIVEL_ENCABEZADO.search(estilo)
        if estilo.lower() == "title" or (coincidencia and coincidencia.group(1) == "1"):
            lineas.append(f"# {texto}")
        elif coincidencia:
            lineas.append(f"{'#' * min(int(coincidencia.group(1)), 3)} {texto}")
        elif "list bullet" in estilo.lower() or "list number" in estilo.lower():
            lineas.append(f"- {texto}")
        else:
            lineas.append(texto)
    return "\n".join(lineas)
