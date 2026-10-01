# Imagen para FABRICA_SANDBOX=docker: donde la fábrica corre las pruebas del
# código que generó un agente. Sin red, raíz de solo lectura y sin
# capacidades (ver adaptadores/ejecutor_pruebas.py::EjecutorDocker).
#
#   docker build -f backend/sandbox.Dockerfile -t orquesta-sandbox:latest backend
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.3.4
USER nobody
WORKDIR /trabajo
