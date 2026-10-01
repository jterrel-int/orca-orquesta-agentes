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
    monkeypatch.setattr(config, "fabrica_sandbox", "docker")

    assert config.advertencias() == []


def test_avisa_si_brain_claude_cli_sin_el_binario(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "brain", "claude-cli")
    monkeypatch.setattr("shutil.which", lambda _: None)

    avisos = config.advertencias()
    assert any("claude-cli" in a for a in avisos)


def test_no_avisa_si_brain_claude_cli_con_el_binario(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "brain", "claude-cli")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(config, "fabrica_sandbox", "docker")

    assert config.advertencias() == []


def test_avisa_si_deploy_enabled_sin_github(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "deploy_enabled", True)
    monkeypatch.setattr(config, "github_repo", None)
    monkeypatch.setattr("shutil.which", lambda _: None)

    avisos = config.advertencias()
    assert any("GITHUB_REPO" in a for a in avisos)
    assert any("'gh'" in a for a in avisos)


def test_no_avisa_de_despliegue_si_esta_apagado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "brain", "scripted")
    monkeypatch.setattr(config, "deploy_enabled", False)
    monkeypatch.setattr("shutil.which", lambda _: None)

    assert config.advertencias() == []


def test_avisa_si_la_fabrica_verifica_codigo_de_un_llm_sin_aislar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "brain", "anthropic")
    monkeypatch.setattr(config, "anthropic_api_key", "sk-ant-lo-que-sea")
    monkeypatch.setattr(config, "fabrica_sandbox", "local")

    assert any("FABRICA_SANDBOX=docker" in a for a in config.advertencias())


def test_avisa_si_openai_compatible_sin_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "brain", "openai-compatible")
    monkeypatch.setattr(config, "openai_compat_api_key", None)

    assert any("OPENAI_COMPAT_API_KEY" in a for a in config.advertencias())
