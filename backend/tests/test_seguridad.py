"""Controles de acceso del borde: anti-CSRF por origen, origen del WebSocket
y token opcional. También los enlaces simbólicos en el espacio de trabajo.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.adaptadores.cerebro_guionado import CerebroGuionado
from app.agents.fabrica.comun import Medidor
from app.agents.fabrica.implementador import Implementador
from app.api.seguridad import control_de_acceso, websocket_permitido
from app.config import config
from app.dominio.fabrica import Consumo, Especificacion, PoliticaFabrica, RespuestaMedida


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(control_de_acceso)

    @app.post("/api/fabrica/linea/reiniciar")
    async def reiniciar() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/health")
    async def salud() -> dict[str, bool]:
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        if not websocket_permitido(socket):
            await socket.close(code=1008)
            return
        await socket.accept()
        await socket.send_text("hola")
        await socket.close()

    return app


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(config, "origenes_permitidos", "http://localhost:3000")
    monkeypatch.setattr(config, "orquesta_token", None)
    return TestClient(_app())


def test_post_desde_otro_origen_se_rechaza(cliente: TestClient) -> None:
    """CSRF: un POST sin cuerpo desde otra página no pasa por preflight."""
    r = cliente.post("/api/fabrica/linea/reiniciar", headers={"Origin": "https://malo.example"})
    assert r.status_code == 403


def test_post_del_panel_o_sin_origen_pasa(cliente: TestClient) -> None:
    assert (
        cliente.post(
            "/api/fabrica/linea/reiniciar", headers={"Origin": "http://localhost:3000"}
        ).status_code
        == 200
    )
    assert cliente.post("/api/fabrica/linea/reiniciar").status_code == 200


def test_websocket_de_otro_origen_se_cierra(cliente: TestClient) -> None:
    malo = {"Origin": "https://malo.example"}
    with (
        pytest.raises(WebSocketDisconnect) as e,
        cliente.websocket_connect("/ws", headers=malo) as ws,
    ):
        ws.receive_text()
    assert e.value.code == 1008
    with cliente.websocket_connect("/ws", headers={"Origin": "http://localhost:3000"}) as ws:
        assert ws.receive_text() == "hola"


def test_con_token_configurado_se_exige(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "orquesta_token", "secreto")
    assert cliente.post("/api/fabrica/linea/reiniciar").status_code == 401
    assert (
        cliente.post(
            "/api/fabrica/linea/reiniciar", headers={"Authorization": "Bearer secreto"}
        ).status_code
        == 200
    )
    # La salud queda abierta para monitoreo.
    assert cliente.get("/api/health").status_code == 200
    with pytest.raises(WebSocketDisconnect), cliente.websocket_connect("/ws") as ws:
        ws.receive_text()
    with cliente.websocket_connect("/ws?token=secreto") as ws:
        assert ws.receive_text() == "hola"


def _enlace(destino: Path, enlace: Path) -> None:
    try:
        os.symlink(destino, enlace)
    except (OSError, NotImplementedError):
        pytest.skip("Este sistema no permite crear enlaces simbólicos sin privilegios")


async def test_el_implementador_no_escribe_ni_lee_a_traves_de_un_enlace(tmp_path: Path) -> None:
    espacio = tmp_path / "espacio"
    (espacio / "src").mkdir(parents=True)
    secreto = tmp_path / ".env"
    secreto.write_text("ANTHROPIC_API_KEY=sk-ant-de-verdad", encoding="utf-8")
    _enlace(secreto, espacio / "src" / "mod.py")

    espec = Especificacion(
        id="S1", titulo="Módulo", descripcion="x", archivos=["src/mod.py", "tests/test_mod.py"]
    )
    espia: list[str] = []

    class Espia(CerebroGuionado):
        async def pensar_medido(
            self, instruccion: str, contexto: str = "", *, respaldo: str = ""
        ) -> RespuestaMedida:
            espia.append(contexto)
            return RespuestaMedida(respaldo, Consumo("guionado"))

    await Implementador(Espia()).implementar(
        espec, espacio, PoliticaFabrica(), motivo_rechazo="", medidor=Medidor()
    )

    assert "sk-ant-de-verdad" not in "".join(espia)
    assert secreto.read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=sk-ant-de-verdad"
    assert not (espacio / "src" / "mod.py").is_symlink()
