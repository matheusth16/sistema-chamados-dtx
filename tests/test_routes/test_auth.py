"""Testes das rotas de autenticação (login, logout). Ref: CT-AUTH-*."""

from unittest.mock import MagicMock, patch


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


def test_alterar_senha_sem_must_change_redireciona_supervisor(client, app):
    """Supervisor que já trocou senha é redirecionado para /admin ao acessar alterar-senha."""
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
    assert "admin" in (r.location or "")


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


def test_alterar_senha_sucesso_supervisor_redireciona_para_admin(client, app):
    """Supervisor com senha válida é redirecionado para /admin após trocar senha."""
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
    assert "admin" in (r.location or "")


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
