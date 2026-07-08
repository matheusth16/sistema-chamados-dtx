"""Testes das rotas de autenticação (login, logout). Ref: CT-AUTH-*."""

from unittest.mock import MagicMock, patch

import pytest


def test_login_get_retorna_200(client):
    """GET /login retorna 200 e página de login."""
    r = client.get("/login")
    assert r.status_code == 200
    assert b"login" in r.data.lower() or b"email" in r.data.lower() or b"Email" in r.data


def test_login_post_sem_credenciais_redireciona_com_flash(client):
    """POST /login sem email/senha redireciona para login."""
    r = client.post("/login", data={}, follow_redirects=False)
    assert r.status_code in (302, 200)
    if r.status_code == 302:
        assert "/login" in r.location


def test_login_post_email_senha_vazios_permanece_em_login(client):
    """CT-AUTH-03: POST /login com email ou senha vazios permanece na página de login com mensagem."""
    r = client.post("/login", data={"email": "", "senha": "qualquer"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"login" in r.data.lower() or b"email" in r.data.lower()

    r2 = client.post("/login", data={"email": "user@test.com", "senha": ""}, follow_redirects=True)
    assert r2.status_code == 200
    assert b"login" in r2.data.lower() or b"email" in r2.data.lower()


def test_login_post_credenciais_invalidas_nao_redireciona_para_index(client):
    """CT-AUTH-04: POST /login com email/senha incorretos não cria sessão; permanece em login."""
    with patch("app.routes.auth.Usuario.get_by_email", return_value=None):
        r = client.post(
            "/login", data={"email": "naoexiste@test.com", "senha": "123"}, follow_redirects=True
        )
    assert r.status_code == 200
    assert b"login" in r.data.lower() or b"email" in r.data.lower()


def test_login_must_change_password_redireciona_para_alterar_senha(client):
    """POST /login com must_change_password=True (non-admin) redireciona para alterar-senha."""
    usuario = MagicMock()
    usuario.id = "u1"
    usuario.email = "u1@test.com"
    usuario.nome = "Usuário Teste"
    usuario.perfil = "solicitante"
    usuario.must_change_password = True
    usuario.get_id = lambda: "u1"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        r = client.post(
            "/login",
            data={"email": "u1@test.com", "senha": "qualquer"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "alterar-senha" in (r.location or "")


def test_login_solicitante_autenticado_redireciona_para_index(client_logado_solicitante):
    """GET /login com solicitante já autenticado redireciona para index (/)."""
    r = client_logado_solicitante.get("/login", follow_redirects=False)
    assert r.status_code == 302
    # Solicitante vai para / não para /admin
    assert "/admin" not in (r.location or "") or r.location == "/"


# ── Alterar senha obrigatória ──────────────────────────────────────────────────


def _create_client_must_change_password(client, app):
    """Cria sessão logada com must_change_password=True (perfil solicitante)."""
    usuario = MagicMock()
    usuario.id = "u_change"
    usuario.email = "change@test.com"
    usuario.nome = "Mudança Obrigatória"
    usuario.perfil = "solicitante"
    usuario.must_change_password = True
    usuario.get_id = lambda: "u_change"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.update = MagicMock(return_value=True)
    usuario.is_admin_or_above = False
    usuario.is_supervisor_or_above = False
    return usuario


def test_alterar_senha_obrigatoria_get_retorna_200(client, app):
    """GET /alterar-senha-obrigatoria com must_change_password=True retorna 200."""
    usuario = _create_client_must_change_password(client, app)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.get("/alterar-senha-obrigatoria", follow_redirects=False)
    assert r.status_code == 200


@pytest.mark.parametrize("perfil", ["admin", "admin_global"])
def test_alterar_senha_obrigatoria_admin_nao_e_isento(client, app, perfil):
    """Admin e admin_global com must_change_password=True também veem o formulário
    (nenhum perfil é isento de trocar a senha no primeiro acesso)."""
    usuario = _create_client_must_change_password(client, app)
    usuario.perfil = perfil
    usuario.is_admin_or_above = True
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
        patch("app.routes.auth._dispositivo_confiavel", return_value=True),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.get("/alterar-senha-obrigatoria", follow_redirects=False)
    assert r.status_code == 200


def test_alterar_senha_campos_vazios_redireciona(client, app):
    """POST /alterar-senha-obrigatoria com campos vazios redireciona com erro."""
    usuario = _create_client_must_change_password(client, app)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "", "confirmar_senha": ""},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_alterar_senha_senha_curta_redireciona(client, app):
    """POST /alterar-senha-obrigatoria com senha < 6 chars redireciona com erro."""
    usuario = _create_client_must_change_password(client, app)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "abc", "confirmar_senha": "abc"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_alterar_senha_senhas_diferentes_redireciona(client, app):
    """POST /alterar-senha-obrigatoria com senhas diferentes redireciona com erro."""
    usuario = _create_client_must_change_password(client, app)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "senha123", "confirmar_senha": "senha456"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_alterar_senha_senha_padrao_bloqueada(client, app):
    """POST /alterar-senha-obrigatoria com senha '123456' é bloqueada."""
    usuario = _create_client_must_change_password(client, app)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "123456", "confirmar_senha": "123456"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_alterar_senha_sucesso_redireciona_para_index(client, app):
    """POST /alterar-senha-obrigatoria com senha válida redireciona para index."""
    usuario = _create_client_must_change_password(client, app)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "NovaSenha2026!", "confirmar_senha": "NovaSenha2026!"},
            follow_redirects=False,
        )
    assert r.status_code == 302

    usuario = MagicMock()
    usuario.check_password = MagicMock(return_value=False)
    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r2 = client.post(
            "/login", data={"email": "existente@test.com", "senha": "errada"}, follow_redirects=True
        )
    assert r2.status_code == 200
    assert (
        b"login" in r2.data.lower()
        or b"email" in r2.data.lower()
        or b"incorretos" in r2.data.lower()
    )


def test_logout_com_usuario_logado_redireciona_para_login(client_logado_solicitante):
    """CT-AUTH-05: GET /logout com usuário logado encerra sessão e redireciona para /login."""
    r = client_logado_solicitante.get("/logout", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location

    # Após logout, acesso a rota protegida deve redirecionar para login
    r2 = client_logado_solicitante.get("/", follow_redirects=False)
    assert r2.status_code == 302
    assert "login" in r2.location


def test_logout_sem_login_redireciona_para_login(client):
    """GET /logout sem estar logado redireciona para login."""
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_index_sem_login_redireciona_para_login(client):
    """CT-AUTH-06: Acesso a / sem autenticação redireciona para login."""
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


# ── Lockout por email (A2) ─────────────────────────────────────────────────────


def test_login_email_bloqueado_redireciona_sem_verificar_senha(client):
    """Login com email bloqueado redireciona para /login sem chamar get_by_email."""
    with (
        patch(
            "app.routes.auth.LoginAttemptTracker.is_locked_out",
            side_effect=lambda x: x == "locked@test.com",
        ),
        patch("app.routes.auth.Usuario.get_by_email") as mock_get,
    ):
        r = client.post(
            "/login",
            data={"email": "locked@test.com", "senha": "qualquer"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "/login" in (r.location or "")
    mock_get.assert_not_called()


def test_login_falha_incrementa_tentativas_para_email(client):
    """Falha de login deve incrementar contador de tentativas para o email além do IP."""
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=None),
        patch("app.routes.auth.LoginAttemptTracker.is_locked_out", return_value=False),
        patch("app.routes.auth.LoginAttemptTracker.increment_attempt", return_value=1) as mock_inc,
        patch("app.routes.auth.LoginAttemptTracker.log_failed_attempt"),
    ):
        client.post(
            "/login",
            data={"email": "usuario@test.com", "senha": "errada"},
            follow_redirects=False,
        )

    args_chamados = [call.args[0] for call in mock_inc.call_args_list]
    assert "usuario@test.com" in args_chamados, "increment_attempt deve ser chamado com o email"


def test_login_falha_aplica_lockout_para_email_apos_max_tentativas(client):
    """Após MAX_LOGIN_ATTEMPTS falhas, lockout é aplicado para email e IP."""
    from app.services.login_attempts import MAX_LOGIN_ATTEMPTS

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=None),
        patch("app.routes.auth.LoginAttemptTracker.is_locked_out", return_value=False),
        patch(
            "app.routes.auth.LoginAttemptTracker.increment_attempt",
            return_value=MAX_LOGIN_ATTEMPTS,
        ),
        patch("app.routes.auth.LoginAttemptTracker.apply_lockout") as mock_lockout,
        patch("app.routes.auth.LoginAttemptTracker.log_failed_attempt"),
    ):
        client.post(
            "/login",
            data={"email": "usuario@test.com", "senha": "errada"},
            follow_redirects=False,
        )

    lockout_ids = [call.args[0] for call in mock_lockout.call_args_list]
    assert "usuario@test.com" in lockout_ids, "apply_lockout deve ser chamado para o email"


def test_login_ip_bloqueado_redireciona_sem_verificar_senha(client):
    """Login com IP bloqueado redireciona para /login sem chamar get_by_email."""
    with (
        patch(
            "app.routes.auth.LoginAttemptTracker.is_locked_out",
            side_effect=lambda x: not x.count("@"),  # IPs não têm '@', emails têm
        ),
        patch("app.routes.auth.Usuario.get_by_email") as mock_get,
    ):
        r = client.post(
            "/login",
            data={"email": "usuario@test.com", "senha": "qualquer"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "/login" in (r.location or "")
    mock_get.assert_not_called()


def test_lockout_nao_bypassado_com_xff_forjado_na_frente(client):
    """ProxyFix(x_for=1): IP falso no início do X-Forwarded-For não é usado para lockout.

    Comportamento esperado com ProxyFix:
    - X-Forwarded-For: "1.2.3.4, 127.0.0.1" → ProxyFix usa o último IP (127.0.0.1)
    - get_client_ip() retorna remote_addr = 127.0.0.1 (controlado pelo proxy)
    - "1.2.3.4" (forjado pelo atacante) é ignorado
    """
    with (
        patch("app.routes.auth.LoginAttemptTracker.is_locked_out", return_value=False),
        patch("app.routes.auth.Usuario.get_by_email", return_value=None),
        patch("app.routes.auth.LoginAttemptTracker.increment_attempt", return_value=1) as mock_inc,
        patch("app.routes.auth.LoginAttemptTracker.log_failed_attempt"),
    ):
        client.post(
            "/login",
            data={"email": "test@test.com", "senha": "errada"},
            headers={"X-Forwarded-For": "1.2.3.4, 127.0.0.1"},
            follow_redirects=False,
        )

    ips_usados = [call.args[0] for call in mock_inc.call_args_list]
    # ProxyFix(x_for=1) toma o último IP do XFF → 127.0.0.1 (REMOTE_ADDR real)
    # O IP forjado "1.2.3.4" (primeiro) NÃO deve ser usado
    assert "1.2.3.4" not in ips_usados, f"IP forjado não deve ser usado; ips={ips_usados}"
    assert "127.0.0.1" in ips_usados, f"REMOTE_ADDR real deve ser usado; ips={ips_usados}"


def test_alterar_senha_sem_must_change_redireciona_supervisor(client, app):
    """Supervisor que já trocou senha é redirecionado para /painel ao acessar alterar-senha."""
    usuario = MagicMock()
    usuario.id = "sup1"
    usuario.email = "sup@test.com"
    usuario.nome = "Supervisor"
    usuario.perfil = "supervisor"
    usuario.must_change_password = False
    usuario.get_id = lambda: "sup1"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post("/login", data={"email": "sup@test.com", "senha": "ok"}, follow_redirects=False)
        r = client.get("/alterar-senha-obrigatoria", follow_redirects=False)

    assert r.status_code == 302
    assert "painel" in (r.location or "")


def test_alterar_senha_sem_letra_redireciona(client, app):
    """POST /alterar-senha-obrigatoria com senha só com dígitos (sem letras) redireciona com erro."""
    usuario = _create_client_must_change_password(client, app)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "change@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "12345678", "confirmar_senha": "12345678"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_alterar_senha_sucesso_supervisor_redireciona_para_painel(client, app):
    """Supervisor com senha válida é redirecionado para /painel após trocar senha."""
    usuario = MagicMock()
    usuario.id = "sup2"
    usuario.email = "sup2@test.com"
    usuario.nome = "Supervisor Dois"
    usuario.perfil = "supervisor"
    usuario.must_change_password = True
    usuario.get_id = lambda: "sup2"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.update = MagicMock(return_value=True)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "sup2@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "NovaSenha2026!", "confirmar_senha": "NovaSenha2026!"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "painel" in (r.location or "")


def test_alterar_senha_solicitante_sem_must_change_redireciona_para_index(client, app):
    """Solicitante que já trocou senha é redirecionado para / ao acessar alterar-senha."""
    usuario = MagicMock()
    usuario.id = "sol10"
    usuario.email = "sol10@test.com"
    usuario.nome = "Solicitante Pronto"
    usuario.perfil = "solicitante"
    usuario.must_change_password = False
    usuario.get_id = lambda: "sol10"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "sol10@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.get("/alterar-senha-obrigatoria", follow_redirects=False)

    assert r.status_code == 302
    assert r.location == "/" or "index" in (r.location or "") or r.location.endswith("/")


def test_alterar_senha_update_retorna_false_redireciona(client, app):
    """Quando current_user.update() retorna False, redireciona com erro."""
    usuario = MagicMock()
    usuario.id = "sup_false"
    usuario.email = "sup_false@test.com"
    usuario.nome = "Supervisor False Update"
    usuario.perfil = "supervisor"
    usuario.must_change_password = True
    usuario.get_id = lambda: "sup_false"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.update = MagicMock(return_value=False)
    usuario.is_admin_or_above = False

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login",
            data={"email": "sup_false@test.com", "senha": "ok"},
            follow_redirects=False,
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "NovaSenha2026!", "confirmar_senha": "NovaSenha2026!"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "alterar-senha" in (r.location or "")


# ── Onda 2: conta desativada (ativo=False) ────────────────────────────────────


def test_login_usuario_inativo_nao_autentica(client):
    """CT-AUTH-I1: Login com ativo=False e senha correta NÃO cria sessão autenticada."""
    usuario = MagicMock()
    usuario.id = "u_inativo"
    usuario.email = "inativo@test.com"
    usuario.nome = "Inativo Teste"
    usuario.perfil = "solicitante"
    usuario.ativo = False
    usuario.must_change_password = False
    usuario.get_id = lambda: "u_inativo"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)

    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r = client.post(
            "/login",
            data={"email": "inativo@test.com", "senha": "ok"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "login" in (r.location or "")

    # Rota protegida ainda deve redirecionar — sessão NÃO foi criada
    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 302
    assert "login" in (r2.location or "")


def test_login_usuario_inativo_exibe_flash_account_disabled(client):
    """CT-AUTH-I2: Login com ativo=False exibe mensagem de conta desativada."""
    usuario = MagicMock()
    usuario.id = "u_inativo2"
    usuario.email = "inativo2@test.com"
    usuario.nome = "Inativo Dois"
    usuario.perfil = "solicitante"
    usuario.ativo = False
    usuario.must_change_password = False
    usuario.get_id = lambda: "u_inativo2"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)

    with patch("app.routes.auth.Usuario.get_by_email", return_value=usuario):
        r = client.post(
            "/login",
            data={"email": "inativo2@test.com", "senha": "ok"},
            follow_redirects=True,
        )

    assert r.status_code == 200
    # "disabled" aparece na mensagem traduzida en: "Account disabled"
    assert b"disabled" in r.data.lower()


def test_login_usuario_inativo_nao_incrementa_lockout(client):
    """CT-AUTH-I3: Login com ativo=False não incrementa contador de brute-force."""
    usuario = MagicMock()
    usuario.ativo = False
    usuario.check_password = MagicMock(return_value=True)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.routes.auth.LoginAttemptTracker.is_locked_out", return_value=False),
        patch("app.routes.auth.LoginAttemptTracker.increment_attempt") as mock_inc,
    ):
        client.post(
            "/login",
            data={"email": "inativo3@test.com", "senha": "ok"},
            follow_redirects=False,
        )

    mock_inc.assert_not_called()


def test_user_loader_usuario_inativo_retorna_none(client, app):
    """CT-AUTH-I4: Sessão ativa é invalidada quando user_loader encontra ativo=False."""
    # Fase 1: login com usuário ativo
    usuario_ativo = MagicMock()
    usuario_ativo.id = "u_loader_inativo"
    usuario_ativo.email = "loader_inativo@test.com"
    usuario_ativo.nome = "Loader Inativo"
    usuario_ativo.perfil = "solicitante"
    usuario_ativo.ativo = True
    usuario_ativo.must_change_password = False
    usuario_ativo.onboarding_perfis_vistos = ["solicitante"]
    usuario_ativo.get_id = lambda: "u_loader_inativo"
    usuario_ativo.is_authenticated = True
    usuario_ativo.is_active = True
    usuario_ativo.is_anonymous = False
    usuario_ativo.check_password = MagicMock(return_value=True)

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario_ativo),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario_ativo),
    ):
        r_login = client.post(
            "/login",
            data={"email": "loader_inativo@test.com", "senha": "ok"},
            follow_redirects=False,
        )
    assert r_login.status_code == 302

    # Fase 2: usuário foi desativado — user_loader deve retornar None
    usuario_inativo = MagicMock()
    usuario_inativo.id = "u_loader_inativo"
    usuario_inativo.ativo = False
    usuario_inativo.get_id = lambda: "u_loader_inativo"
    usuario_inativo.is_authenticated = True
    usuario_inativo.is_active = True
    usuario_inativo.is_anonymous = False
    usuario_inativo.must_change_password = False

    with patch("app.models_usuario.Usuario.get_by_id", return_value=usuario_inativo):
        r = client.get("/", follow_redirects=False)

    assert r.status_code == 302
    assert "login" in (r.location or "")


def test_alterar_senha_excecao_no_update_redireciona(client, app):
    """Exceção em current_user.update redireciona de volta para alterar-senha."""
    usuario = MagicMock()
    usuario.id = "sup3"
    usuario.email = "sup3@test.com"
    usuario.nome = "Supervisor Três"
    usuario.perfil = "supervisor"
    usuario.must_change_password = True
    usuario.get_id = lambda: "sup3"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.update = MagicMock(side_effect=Exception("Firestore error"))
    usuario.is_admin_or_above = False

    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        client.post(
            "/login", data={"email": "sup3@test.com", "senha": "ok"}, follow_redirects=False
        )
        r = client.post(
            "/alterar-senha-obrigatoria",
            data={"nova_senha": "NovaSenha2026!", "confirmar_senha": "NovaSenha2026!"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "alterar-senha" in (r.location or "")


# ── Onda 4: login via email_lookup_hash ────────────────────────────────────────


def test_login_funciona_quando_get_by_email_usa_hash_lookup(client):
    """Onda 4: login funciona mesmo quando get_by_email usa hash lookup internamente.

    Testa que o fluxo de autenticação (route → get_by_email → check_password)
    é transparente ao mecanismo de lookup (hash vs. plaintext).
    """
    usuario = MagicMock()
    usuario.id = "u_hash_login"
    usuario.email = "hash_user@dtx.aero"
    usuario.nome = "Hash Login User"
    usuario.perfil = "solicitante"
    usuario.must_change_password = False
    usuario.get_id = lambda: "u_hash_login"
    usuario.is_authenticated = True
    usuario.is_active = True
    usuario.is_anonymous = False
    usuario.check_password = MagicMock(return_value=True)
    usuario.ativo = True
    usuario.onboarding_perfis_vistos = ["solicitante"]
    usuario.onboarding_passo = 0
    usuario.is_admin_or_above = False
    usuario.is_supervisor_or_above = False

    # Simula get_by_email usando hash lookup (retorna usuário normalmente)
    with (
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        r = client.post(
            "/login",
            data={"email": "hash_user@dtx.aero", "senha": "SenhaValida123!"},
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "/login" not in (r.location or "")


# ── SSO Microsoft ──────────────────────────────────────────────────────────────


class _FakeThread:
    """Thread fake para executar target imediatamente nos testes."""

    def __init__(self, target=None, daemon=None):
        self._target = target
        self.daemon = daemon

    def start(self):
        if self._target:
            self._target()


def _usuario_existente_mock(
    uid="u_sso", email="sso@dtx.aero", perfil="solicitante", mfa_enabled=False, ativo=True
):
    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = "SSO User"
    u.perfil = perfil
    u.must_change_password = False
    u.mfa_enabled = mfa_enabled
    u.ativo = ativo
    u.is_authenticated = True
    u.is_active = True
    u.is_anonymous = False
    u.get_id = lambda: str(uid)
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.is_gestor = False
    return u


def test_login_microsoft_redireciona_para_authorize_url(client):
    """GET /login/microsoft redireciona para a authorize URL do MSAL e guarda o flow na sessão."""
    fake_flow = {"state": "abc123"}
    with patch(
        "app.routes.auth.sso_microsoft_service.iniciar_fluxo_login",
        return_value=("https://login.microsoftonline.com/authorize?x=1", fake_flow),
    ):
        r = client.get("/login/microsoft", follow_redirects=False)

    assert r.status_code == 302
    assert r.location == "https://login.microsoftonline.com/authorize?x=1"
    with client.session_transaction() as sess:
        assert sess.get("sso_flow") == fake_flow


def test_login_microsoft_desabilitado_flash_e_redireciona(client, app):
    """GET /login/microsoft com SSO_MICROSOFT_ENABLED=False redireciona para /login."""
    app.config["SSO_MICROSOFT_ENABLED"] = False
    r = client.get("/login/microsoft", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.location


def test_login_microsoft_host_diferente_do_redirect_uri_normaliza_antes_do_flow(client, app):
    """Acessar via host != host do SSO_REDIRECT_URI (ex: 127.0.0.1 vs localhost) deve
    redirecionar para o host correto ANTES de iniciar o flow OAuth — caso contrário o
    cookie de sessão com 'sso_flow' é gravado no host errado e o callback (que sempre
    volta para o host de SSO_REDIRECT_URI) chega sem sessão, falhando o login.
    """
    app.config["SSO_REDIRECT_URI"] = "http://localhost:5000/login/microsoft/callback"
    with patch("app.routes.auth.sso_microsoft_service.iniciar_fluxo_login") as mock_iniciar:
        r = client.get("/login/microsoft", base_url="http://127.0.0.1:5000", follow_redirects=False)

    assert r.status_code == 302
    assert r.location.startswith("http://localhost:5000/login/microsoft")
    mock_iniciar.assert_not_called()
    with client.session_transaction() as sess:
        assert "sso_flow" not in sess


def test_callback_sem_flow_na_sessao_redireciona_login(client):
    """GET callback sem flow salvo na sessão redireciona para /login."""
    r = client.get("/login/microsoft/callback", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.location


def test_callback_erro_query_param_redireciona_login(client):
    """GET callback com ?error= (usuário cancelou) redireciona para /login."""
    with client.session_transaction() as sess:
        sess["sso_flow"] = {"state": "abc"}
    r = client.get("/login/microsoft/callback?error=access_denied", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.location


def test_callback_token_exchange_falha_redireciona_login(client):
    """GET callback com falha na troca de token (MSAL retorna 'error') redireciona para /login."""
    with client.session_transaction() as sess:
        sess["sso_flow"] = {"state": "abc"}
    with patch(
        "app.routes.auth.sso_microsoft_service.concluir_fluxo_login",
        return_value={"error": "invalid_grant", "error_description": "code expired"},
    ):
        r = client.get("/login/microsoft/callback?code=xyz&state=abc", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.location


def test_callback_tenant_incorreto_rejeita_login_sem_tocar_firestore(client):
    """Tenant mismatch rejeita login ANTES de qualquer acesso a Usuario (get_by_email/save)."""
    with client.session_transaction() as sess:
        sess["sso_flow"] = {"state": "abc"}
    with (
        patch(
            "app.routes.auth.sso_microsoft_service.concluir_fluxo_login",
            return_value={"id_token_claims": {"tid": "outro-tenant"}},
        ),
        patch("app.routes.auth.sso_microsoft_service.validar_tenant", return_value=False),
        patch("app.routes.auth.Usuario.get_by_email") as mock_get_by_email,
        patch("app.routes.auth.Usuario.save") as mock_save,
    ):
        r = client.get("/login/microsoft/callback?code=xyz&state=abc", follow_redirects=False)

    assert r.status_code == 302
    assert "/login" in r.location
    mock_get_by_email.assert_not_called()
    mock_save.assert_not_called()


def test_callback_usuario_existente_faz_login_sem_duplicar(client):
    """Usuário existente por e-mail faz login na MESMA conta — MFA gate ainda se aplica."""
    usuario = _usuario_existente_mock(mfa_enabled=False)
    with (
        client.session_transaction() as sess,
    ):
        sess["sso_flow"] = {"state": "abc"}
    with (
        patch(
            "app.routes.auth.sso_microsoft_service.concluir_fluxo_login",
            return_value={
                "id_token_claims": {"tid": "tenant-dtx", "preferred_username": usuario.email}
            },
        ),
        patch("app.routes.auth.sso_microsoft_service.validar_tenant", return_value=True),
        patch(
            "app.routes.auth.sso_microsoft_service.extrair_identidade",
            return_value=(usuario.email, usuario.nome),
        ),
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario) as mock_get_by_email,
        patch("app.routes.auth.Usuario.save") as mock_save,
        patch("app.models_usuario.Usuario.get_by_id", return_value=usuario),
    ):
        r = client.get("/login/microsoft/callback?code=xyz&state=abc", follow_redirects=False)

    assert r.status_code == 302
    assert "mfa" in (r.location or "").lower()
    mock_get_by_email.assert_called_once()
    mock_save.assert_not_called()


def test_callback_usuario_desativado_bloqueia_login(client):
    """Usuário existente com ativo=False é bloqueado, mesmo com token Microsoft válido."""
    usuario = _usuario_existente_mock(ativo=False)
    with client.session_transaction() as sess:
        sess["sso_flow"] = {"state": "abc"}
    with (
        patch(
            "app.routes.auth.sso_microsoft_service.concluir_fluxo_login",
            return_value={"id_token_claims": {"tid": "tenant-dtx"}},
        ),
        patch("app.routes.auth.sso_microsoft_service.validar_tenant", return_value=True),
        patch(
            "app.routes.auth.sso_microsoft_service.extrair_identidade",
            return_value=(usuario.email, usuario.nome),
        ),
        patch("app.routes.auth.Usuario.get_by_email", return_value=usuario),
    ):
        r = client.get("/login/microsoft/callback?code=xyz&state=abc", follow_redirects=False)

    assert r.status_code == 302
    assert "/login" in r.location


def test_callback_usuario_novo_auto_provisiona_como_solicitante(client, app):
    """E-mail sem Usuario existente auto-provisiona perfil solicitante e dispara notificações."""
    from app.models_usuario import Usuario

    admin_mock = _usuario_existente_mock(uid="admin_1", email="admin@dtx.aero", perfil="admin")

    with client.session_transaction() as sess:
        sess["sso_flow"] = {"state": "abc"}
    with (
        patch(
            "app.routes.auth.sso_microsoft_service.concluir_fluxo_login",
            return_value={"id_token_claims": {"tid": "tenant-dtx"}},
        ),
        patch("app.routes.auth.sso_microsoft_service.validar_tenant", return_value=True),
        patch(
            "app.routes.auth.sso_microsoft_service.extrair_identidade",
            return_value=("novo.sso@dtx.aero", "Novo SSO"),
        ),
        patch("app.routes.auth.Usuario.get_by_email", return_value=None),
        patch.object(Usuario, "save", autospec=True) as mock_save,
        patch("app.routes.auth.Usuario.get_all", return_value=[admin_mock]),
        patch("app.routes.auth.cache_delete"),
        patch("app.routes.auth.notificar_novo_usuario_sso") as mock_notif_user,
        patch("app.routes.auth.notificar_admins_novo_usuario_sso") as mock_notif_admins,
        patch("app.routes.auth.threading.Thread", side_effect=_FakeThread),
    ):
        r = client.get("/login/microsoft/callback?code=xyz&state=abc", follow_redirects=False)

    assert r.status_code == 302
    assert "mfa" in (r.location or "").lower()

    mock_save.assert_called_once()
    novo_usuario = mock_save.call_args[0][0]
    assert novo_usuario.email == "novo.sso@dtx.aero"
    assert novo_usuario.perfil == "solicitante"
    assert novo_usuario.auth_provider == "microsoft"

    mock_notif_user.assert_called_once()
    mock_notif_admins.assert_called_once()
    admins_kwargs = mock_notif_admins.call_args.kwargs
    assert admins_kwargs["admin_emails"] == ["admin@dtx.aero"]
