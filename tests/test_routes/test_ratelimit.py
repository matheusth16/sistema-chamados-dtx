"""Testes de rate limiting nas rotas de API.

Usa fixture `app_rl` que habilita rate limiting via Config antes de create_app().
"""

import pytest


@pytest.fixture
def app_rl():
    """App com rate limiting ativado (in-memory, sem Redis)."""
    import config as cfg
    from app.limiter import limiter as _limiter

    old_enabled = cfg.Config.RATELIMIT_ENABLED
    old_limiter_enabled = _limiter.enabled

    cfg.Config.RATELIMIT_ENABLED = True
    cfg.Config.RATELIMIT_STORAGE_URL = "memory://"
    cfg.Config.RATELIMIT_STORAGE_URI = "memory://"

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["APP_BASE_URL"] = ""

    yield app

    import contextlib

    with contextlib.suppress(Exception):
        _limiter.reset()
    _limiter.enabled = old_limiter_enabled
    cfg.Config.RATELIMIT_ENABLED = old_enabled


@pytest.fixture
def client_rl(app_rl):
    return app_rl.test_client()


# ── /api/csp-report ───────────────────────────────────────────────────────────


def test_csp_report_aceita_requisicao_normal(client_rl):
    """POST /api/csp-report aceita requisições dentro do limite."""
    r = client_rl.post(
        "/api/csp-report",
        json={"csp-report": {"blocked-uri": "eval"}},
        content_type="application/json",
    )
    assert r.status_code == 204


def test_csp_report_retorna_429_apos_exceder_limite(client_rl):
    """POST /api/csp-report retorna 429 após exceder 20 requisições por minuto."""
    status_codes = set()
    for _ in range(25):
        r = client_rl.post(
            "/api/csp-report",
            json={"csp-report": {"blocked-uri": "eval"}},
            content_type="application/json",
        )
        status_codes.add(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in status_codes, f"Esperava 429 mas obteve apenas: {status_codes}"


# ── /api/atualizar-status ─────────────────────────────────────────────────────


def test_atualizar_status_retorna_429_apos_exceder_limite(app_rl):
    """POST /api/atualizar-status retorna 429 após exceder 30 req/min (usuário autenticado)."""
    from unittest.mock import MagicMock, patch

    usuario = MagicMock()
    usuario.id = "u_rl"
    usuario.email = "rl@test.com"
    usuario.nome = "RL User"
    usuario.perfil = "supervisor"
    usuario.must_change_password = False
    usuario.get_id = lambda: "u_rl"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
        patch("app.routes.auth.LoginAttemptTracker.is_locked_out", return_value=False),
        patch("app.routes.auth.LoginAttemptTracker.reset_attempts"),
        patch("app.routes.auth.LoginAttemptTracker.log_success_attempt"),
    ):
        client = app_rl.test_client()
        client.post("/login", data={"email": "rl@test.com", "senha": "ok"})

        status_codes = set()
        for _ in range(35):
            r = client.post(
                "/api/atualizar-status",
                json={"chamado_id": "ch1", "novo_status": "Aberto"},
                content_type="application/json",
            )
            status_codes.add(r.status_code)
            if r.status_code == 429:
                break

    assert 429 in status_codes, f"Esperava 429 mas obteve apenas: {status_codes}"
