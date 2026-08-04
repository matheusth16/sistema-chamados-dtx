"""Testes do serviço de onboarding (Fase 2, Marco 10 — Postgres real)."""

import pytest

from app.models_usuario import Usuario

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_usuario(**overrides):
    defaults = {
        "id": "u1",
        "email": "onboarding@test.com",
        "nome": "Usuario Onboarding",
        "perfil": "solicitante",
        "onboarding_passo": 1,
    }
    defaults.update(overrides)
    u = Usuario(**defaults)
    assert u.save()
    return u


# ── avancar_passo ──────────────────────────────────────────────────────────────


def test_avancar_passo_sucesso_retorna_true():
    """avancar_passo persiste o novo passo e retorna True."""
    from app.services.onboarding_service import avancar_passo

    _criar_usuario()

    assert avancar_passo("u1", 3) is True
    assert Usuario.get_by_id("u1").onboarding_passo == 3


def test_avancar_passo_usuario_inexistente_retorna_false():
    """avancar_passo retorna False quando o usuário não existe."""
    from app.services.onboarding_service import avancar_passo

    assert avancar_passo("nao_existe", 2) is False


def test_avancar_passo_excecao_retorna_false(monkeypatch):
    """avancar_passo retorna False quando o banco lança exceção."""
    from app.services import onboarding_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(onboarding_service.db_module, "SessionLocal", _explode)

    assert onboarding_service.avancar_passo("u1", 2) is False


# ── concluir_onboarding ──────────────────────────────────────────────────────


def test_concluir_onboarding_sucesso_retorna_true():
    """concluir_onboarding adiciona o perfil a onboarding_perfis_vistos e zera o passo."""
    from app.services.onboarding_service import concluir_onboarding

    _criar_usuario(onboarding_perfis_vistos=[], onboarding_passo=4)

    assert concluir_onboarding("u1", "solicitante") is True
    atualizado = Usuario.get_by_id("u1")
    assert atualizado.onboarding_perfis_vistos == ["solicitante"]
    assert atualizado.onboarding_passo == 0


def test_concluir_onboarding_idempotente_nao_duplica():
    """Perfil já visto não é duplicado em onboarding_perfis_vistos (equivalente ao ArrayUnion)."""
    from app.services.onboarding_service import concluir_onboarding

    _criar_usuario(onboarding_perfis_vistos=["solicitante"])

    assert concluir_onboarding("u1", "solicitante") is True
    assert Usuario.get_by_id("u1").onboarding_perfis_vistos == ["solicitante"]


def test_concluir_onboarding_usuario_inexistente_retorna_false():
    """concluir_onboarding retorna False quando o usuário não existe."""
    from app.services.onboarding_service import concluir_onboarding

    assert concluir_onboarding("nao_existe", "solicitante") is False


def test_concluir_onboarding_excecao_retorna_false(monkeypatch):
    """concluir_onboarding retorna False quando o banco lança exceção."""
    from app.services import onboarding_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(onboarding_service.db_module, "SessionLocal", _explode)

    assert onboarding_service.concluir_onboarding("u1", "solicitante") is False
