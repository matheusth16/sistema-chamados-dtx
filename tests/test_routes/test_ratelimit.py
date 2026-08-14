"""Testes de rate limiting nas rotas de API.

Usa fixture `app_rl` que habilita rate limiting via Config antes de create_app().
"""

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app_rl():
    """App com rate limiting ativado (in-memory, sem Redis).

    Modifica diretamente o Config usado por create_app() (app.__init__.Config),
    não config.Config, para ser imune a reloads de config.py feitos por outros testes.
    """
    import contextlib

    import app as _app_module
    from app.limiter import limiter as _limiter

    old_enabled = _app_module.Config.RATELIMIT_ENABLED
    old_storage_url = _app_module.Config.RATELIMIT_STORAGE_URL
    old_storage_uri = _app_module.Config.RATELIMIT_STORAGE_URI
    old_default = _app_module.Config.RATELIMIT_DEFAULT
    old_limiter_enabled = _limiter.enabled

    _app_module.Config.RATELIMIT_ENABLED = True
    _app_module.Config.RATELIMIT_DEFAULT = "2 per minute"
    _app_module.Config.RATELIMIT_STORAGE_URL = "memory://"
    _app_module.Config.RATELIMIT_STORAGE_URI = "memory://"

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["APP_BASE_URL"] = ""

    yield app

    with contextlib.suppress(Exception):
        _limiter.reset()
    _limiter.enabled = old_limiter_enabled
    _app_module.Config.RATELIMIT_ENABLED = old_enabled
    _app_module.Config.RATELIMIT_STORAGE_URL = old_storage_url
    _app_module.Config.RATELIMIT_STORAGE_URI = old_storage_uri
    _app_module.Config.RATELIMIT_DEFAULT = old_default


@pytest.fixture
def client_rl(app_rl):
    return app_rl.test_client()


def _usuario_rl(uid="u_rl"):
    usuario = MagicMock()
    usuario.id = uid
    usuario.email = f"{uid}@test.com"
    usuario.nome = "RL User"
    usuario.perfil = "supervisor"
    usuario.areas = ["Manutencao"]
    usuario.must_change_password = False
    usuario.mfa_enabled = True
    usuario.get_id.return_value = uid
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    return usuario


def _autenticar_sessao(client, uid="u_rl"):
    with client.session_transaction() as sess:
        sess["_user_id"] = uid
        sess["_fresh"] = True


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


def test_ratelimit_default_configurado_e_aplicado(client_rl):
    respostas = [client_rl.get("/api/push-vapid-public") for _ in range(3)]

    assert [r.status_code for r in respostas[:2]] == [401, 401]
    assert respostas[2].status_code == 429


def test_chave_rate_limit_pre_auth_usa_ip_puro(app_rl):
    from app.limiter import rate_limit_key

    with app_rl.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.113.10"}):
        assert rate_limit_key() == "203.0.113.10"


def test_chave_rate_limit_pos_login_combina_ip_e_usuario(app_rl):
    from app.limiter import rate_limit_key

    usuario = _usuario_rl("usuario-123")
    with (
        app_rl.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.113.10"}),
        patch("app.limiter.current_user", usuario),
    ):
        assert rate_limit_key() == "203.0.113.10:user:usuario-123"


@pytest.mark.parametrize(
    ("rota", "patch_alvo"),
    [
        ("/api/usuarios/buscar", None),
        (
            "/api/supervisores/lista?area=Manutencao",
            "app.routes.api_chamados.Usuario.get_supervisores_por_area",
        ),
    ],
)
def test_endpoints_de_enumeracao_tem_limite_dedicado(app_rl, rota, patch_alvo):
    client = app_rl.test_client()
    usuario = _usuario_rl()
    _autenticar_sessao(client)

    patches = [patch("app.models_usuario.Usuario.get_by_id", return_value=usuario)]
    if patch_alvo:
        patches.append(patch(patch_alvo, return_value=[]))

    with patches[0]:
        contexto_extra = patches[1] if len(patches) > 1 else nullcontext()
        with contexto_extra:
            respostas = [client.get(rota) for _ in range(6)]

    assert all(r.status_code != 429 for r in respostas[:5])
    assert respostas[-1].status_code == 429


# ── /api/atualizar-status ─────────────────────────────────────────────────────


def test_atualizar_status_retorna_429_apos_exceder_limite(app_rl, db_engine):
    """POST /api/atualizar-status retorna 429 após exceder 30 req/min (usuário autenticado).

    chamado_id="ch1" não existe no Postgres de teste — Chamado.get_by_id retorna
    None e a rota responde 404, o que já é suficiente pra contar contra o rate
    limiter (não precisa de chamado real pra este teste).
    """
    from unittest.mock import MagicMock, patch

    usuario = MagicMock()
    usuario.id = "u_rl"
    usuario.email = "rl@test.com"
    usuario.nome = "RL User"
    usuario.perfil = "supervisor"
    usuario.must_change_password = False
    usuario.mfa_enabled = True
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
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
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
