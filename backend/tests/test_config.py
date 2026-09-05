"""config.advertencias(): configuración que arranca igual pero no es la esperada."""

from __future__ import annotations

import pytest

from app.config import config


def test_sin_advertencias_con_la_config_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "brain", "scripted")
    monkeypatch.setattr(config, "deploy_enabled", False)

    assert config.advertencias() == []


def test_avisa_si_brain_anthropic_sin_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "brain", "anthropic")
    monkeypatch.setattr(config, "anthropic_api_key", None)

    avisos = config.advertencias()
    assert any("ANTHROPIC_API_KEY" in a for a in avisos)


def test_no_avisa_si_brain_anthropic_con_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "brain", "anthropic")
    monkeypatch.setattr(config, "anthropic_api_key", "sk-ant-lo-que-sea")

    assert config.advertencias() == []


def test_avisa_si_deploy_enabled_sin_cli_de_vercel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "deploy_enabled", True)
    monkeypatch.setattr("shutil.which", lambda _: None)

    avisos = config.advertencias()
    assert any("CLI de Vercel" in a for a in avisos)


def test_no_avisa_de_vercel_si_deploy_esta_apagado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "deploy_enabled", False)
    monkeypatch.setattr("shutil.which", lambda _: None)

    assert config.advertencias() == []
