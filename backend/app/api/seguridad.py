"""Controles de acceso del borde HTTP/WS. Sin reglas de negocio: solo decide
si una petición puede entrar.

1. Origen (anti-CSRF). CORS no protege los POST "simples" — sin cuerpo JSON,
   como /reanudar, /aprobar o /linea/reiniciar —: el navegador los manda sin
   preflight y el servidor los ejecuta aunque la respuesta no se pueda leer.
   Cualquier página abierta en el mismo navegador podía aprobar una
   especificación riesgosa o reiniciar la línea contra localhost:8000. Por eso
   todo método que cambia estado con una cabecera Origin ajena se rechaza.
   Las peticiones sin Origin (curl, scripts, pruebas) pasan: no vienen de un
   navegador engañado.
2. WebSocket. CORS tampoco aplica a /ws: sin verificar el Origin, cualquier
   página podía escuchar la telemetría de la fábrica (Cross-Site WebSocket
   Hijacking).
3. Token opcional (ORQUESTA_TOKEN). Para cuando el backend escucha en algo que
   no es localhost.
"""

import hmac

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint

from ..config import config

_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})
# Sin token: /api/health para monitoreo y el callback OAuth, que llega por
# redirección de Vercel y no puede llevar cabeceras propias.
_SIN_TOKEN = ("/api/health", "/api/vercel/oauth/callback")


def origen_permitido(origen: str | None) -> bool:
    if not origen:
        return True
    permitidos = config.lista_origenes
    return "*" in permitidos or origen.rstrip("/") in {o.rstrip("/") for o in permitidos}


def token_valido(cabecera: str | None, consulta: str | None) -> bool:
    esperado = config.orquesta_token
    if not esperado:
        return True
    recibido = ""
    if cabecera and cabecera.lower().startswith("bearer "):
        recibido = cabecera[7:].strip()
    elif consulta:
        recibido = consulta
    return hmac.compare_digest(recibido.encode(), esperado.encode())


async def control_de_acceso(request: Request, siguiente: RequestResponseEndpoint) -> Response:
    ruta = request.url.path
    if ruta.startswith("/api/"):
        if request.method not in _SEGUROS and not origen_permitido(request.headers.get("origin")):
            return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
        if (
            request.method != "OPTIONS"
            and not ruta.startswith(_SIN_TOKEN)
            and not token_valido(
                request.headers.get("authorization"), request.query_params.get("token")
            )
        ):
            return JSONResponse({"detail": "Falta el token de acceso o no es válido"}, 401)
    return await siguiente(request)


def websocket_permitido(ws: WebSocket) -> bool:
    return origen_permitido(ws.headers.get("origin")) and token_valido(
        None, ws.query_params.get("token")
    )
