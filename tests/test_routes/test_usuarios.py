"""Testes das rotas de administração de usuários (/admin/usuarios). Requer perfil admin."""

from unittest.mock import patch


class _FakeThread:
    """Thread fake para executar target imediatamente nos testes."""

    def __init__(self, target=None, daemon=None):
        self._target = target
        self.daemon = daemon

    def start(self):
        if self._target:
            self._target()


def test_admin_usuarios_sem_login_redireciona_para_login(client):
    """GET /admin/usuarios sem estar logado redireciona para /login."""
    r = client.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_admin_usuarios_com_solicitante_nao_acessa(client_logado_solicitante):
    """GET /admin/usuarios com perfil solicitante não acessa: 403 ou 302 (ex.: redirect troca de senha)."""
    r = client_logado_solicitante.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert "/admin/usuarios" not in (r.location or "")


def test_admin_usuarios_com_supervisor_nao_acessa(client_logado_supervisor):
    """GET /admin/usuarios com perfil supervisor não acessa: 403 ou 302."""
    r = client_logado_supervisor.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert "/admin/usuarios" not in (r.location or "")


def test_admin_usuarios_com_admin_retorna_200(client_logado_admin):
    """GET /admin/usuarios com perfil admin retorna 200 e página de usuários."""
    with patch("app.routes.usuarios.Usuario.get_all") as mock_get_all:
        mock_get_all.return_value = []
        r = client_logado_admin.get("/admin/usuarios", follow_redirects=False)
    assert r.status_code == 200
    assert b"usuarios" in r.data.lower() or b"user" in r.data.lower()


def test_admin_usuarios_novo_sem_login_redireciona(client):
    """GET /admin/usuarios/novo sem login redireciona para login."""
    r = client.get("/admin/usuarios/novo", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_admin_usuarios_novo_com_admin_retorna_200(client_logado_admin):
    """GET /admin/usuarios/novo com admin retorna formulário."""
    r = client_logado_admin.get("/admin/usuarios/novo", follow_redirects=False)
    assert r.status_code == 200


def test_admin_cria_usuario_dispara_thread_notificacao(client_logado_admin):
    """POST /admin/usuarios (acao=criar) dispara thread de notificação ao novo usuário."""
    with (
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.save"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.threading.Thread") as mock_thread,
    ):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo.usuario@dtx.aero",
                "nome": "Novo Usuario",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    assert mock_thread.return_value.start.call_count >= 1


def test_admin_cria_usuario_chama_notificacao_novo_usuario(client_logado_admin):
    """POST criar usuário deve acionar notificação ao novo usuário."""
    with (
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.save"),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
        patch("app.routes.usuarios.notificar_novo_usuario_cadastrado") as mock_notificar,
        patch("app.routes.usuarios.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo.usuario@dtx.aero",
                "nome": "Novo Usuario",
                "perfil": "solicitante",
                "areas": ["Manutencao"],
            },
            follow_redirects=False,
        )

    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")
    mock_notificar.assert_called_once()
    kwargs = mock_notificar.call_args.kwargs
    assert kwargs["usuario_email"] == "novo.usuario@dtx.aero"
    assert kwargs["perfil"] == "solicitante"
    assert "senha_inicial" in kwargs
    assert kwargs["senha_inicial"] != "123456"
    assert len(kwargs["senha_inicial"]) == 10


# ── Validação de criação ───────────────────────────────────────────────────────


def test_criar_usuario_email_invalido_redireciona_com_erro(client_logado_admin):
    """POST criar com email sem @ redireciona com flash de erro."""
    r = client_logado_admin.post(
        "/admin/usuarios",
        data={
            "acao": "criar",
            "email": "emailinvalido",
            "nome": "Fulano Tal",
            "perfil": "solicitante",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_criar_usuario_email_ja_existe_redireciona(client_logado_admin):
    """POST criar com email duplicado redireciona com erro email_exists."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=True):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "dup@dtx.aero",
                "nome": "Fulano Tal",
                "perfil": "solicitante",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_usuario_nome_curto_redireciona(client_logado_admin):
    """POST criar com nome < 3 chars redireciona com erro name_min_chars."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=False):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={"acao": "criar", "email": "ok@dtx.aero", "nome": "AB", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_usuario_perfil_invalido_redireciona(client_logado_admin):
    """POST criar com perfil inválido redireciona com erro invalid_profile."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=False):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "ok@dtx.aero",
                "nome": "Nome Valido",
                "perfil": "hacker",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_criar_usuario_supervisor_sem_area_redireciona(client_logado_admin):
    """POST criar supervisor sem área redireciona com erro area_required_for_supervisor."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=False):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "sup@dtx.aero",
                "nome": "Supervisor Tal",
                "perfil": "supervisor",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302


# ── Editar usuário ─────────────────────────────────────────────────────────────


def _usuario_fake(
    uid="u1", email="u@dtx.aero", nome="Usuario Fake", perfil="solicitante", areas=None
):
    from unittest.mock import MagicMock

    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = nome
    u.perfil = perfil
    u.areas = areas or []
    # Necessário para que o middleware de autenticação não redirecione para troca de senha
    u.must_change_password = False
    u.is_authenticated = True
    u.get_id = lambda: str(uid)
    return u


def _admin_mock_para_flask_login():
    """Cria um mock do admin com o mesmo UID usado no conftest (admin_1)."""
    from unittest.mock import MagicMock

    a = MagicMock()
    a.id = "admin_1"
    a.email = "admin@test.com"
    a.nome = "Admin Teste"
    a.perfil = "admin"
    a.must_change_password = False
    a.is_authenticated = True
    a.get_id = lambda: "admin_1"
    return a


def _get_by_id_side_effect(target_uid, target_user):
    """Retorna side_effect: admin mock para chamadas do Flask-Login, fake para a rota."""
    admin = _admin_mock_para_flask_login()

    def _side_effect(uid):
        return target_user if uid == target_uid else admin

    return _side_effect


def test_editar_usuario_get_retorna_200(client_logado_admin):
    """GET /admin/usuarios/<id>/editar retorna formulário 200."""
    fake = _usuario_fake(uid="u1")
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u1", fake)
        ),
        patch("app.routes.usuarios.CategoriaSetor.get_all", return_value=[]),
    ):
        r = client_logado_admin.get("/admin/usuarios/u1/editar", follow_redirects=False)
    assert r.status_code == 200


def test_editar_usuario_nao_encontrado_redireciona(client_logado_admin):
    """GET editar com ID inexistente redireciona com erro user_not_found."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.get("/admin/usuarios/naoexiste/editar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_editar_usuario_post_sucesso(client_logado_admin):
    """POST editar com dados válidos redireciona e atualiza o usuário."""
    fake = _usuario_fake(uid="u2", email="u2@dtx.aero", nome="Usuario Dois", perfil="solicitante")
    with (
        patch("app.routes.usuarios.Usuario.get_by_id", return_value=fake),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        fake.update = lambda **kw: None
        fake.areas = []
        r = client_logado_admin.post(
            "/admin/usuarios/u2/editar",
            data={"email": "u2novo@dtx.aero", "nome": "Usuario Dois Novo", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_editar_usuario_post_nome_curto_redireciona(client_logado_admin):
    """POST editar com nome < 3 chars redireciona com erro."""
    fake = _usuario_fake()
    with patch("app.routes.usuarios.Usuario.get_by_id", return_value=fake):
        r = client_logado_admin.post(
            "/admin/usuarios/u1/editar",
            data={"email": "u@dtx.aero", "nome": "AB", "perfil": "solicitante"},
            follow_redirects=False,
        )
    assert r.status_code == 302


# ── Deletar usuário ────────────────────────────────────────────────────────────


def test_deletar_usuario_sucesso(client_logado_admin):
    """POST deletar com ID existente (não admin@dtx.aero) redireciona com sucesso."""
    fake = _usuario_fake(uid="u3", email="u3@dtx.aero", nome="A Deletar")
    fake.delete = lambda: None
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u3", fake)
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u3/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_deletar_usuario_nao_encontrado_redireciona(client_logado_admin):
    """POST deletar com ID inexistente redireciona com erro user_not_found."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "naoexiste" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/naoexiste/deletar", follow_redirects=False)
    assert r.status_code == 302


def test_deletar_usuario_root_admin_bloqueado(client_logado_admin):
    """POST deletar admin@dtx.aero é bloqueado (cannot_delete_root_admin)."""
    fake_root = _usuario_fake(uid="root", email="admin@dtx.aero", nome="Root Admin")
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=_get_by_id_side_effect("root", fake_root),
    ):
        r = client_logado_admin.post("/admin/usuarios/root/deletar", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


# ── Resetar senha ──────────────────────────────────────────────────────────────


def test_resetar_senha_sucesso(client_logado_admin):
    """POST resetar-senha de outro usuário dispara thread e redireciona."""
    fake = _usuario_fake(uid="u4", email="u4@dtx.aero", nome="Usuario Quatro")
    fake.set_password = lambda s: None
    fake.update = lambda **kw: None
    fake.areas = []
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u4", fake)
        ),
        patch("app.routes.usuarios.threading.Thread") as mock_thread,
    ):
        r = client_logado_admin.post("/admin/usuarios/u4/resetar-senha", follow_redirects=False)
    assert r.status_code == 302
    assert mock_thread.return_value.start.call_count >= 1


def test_resetar_senha_usuario_nao_encontrado(client_logado_admin):
    """POST resetar-senha de ID inexistente redireciona com erro."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "nao" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/nao/resetar-senha", follow_redirects=False)
    assert r.status_code == 302


# ── Resetar EXP ───────────────────────────────────────────────────────────────


def test_resetar_exp_sucesso(client_logado_admin):
    """POST reset-exp de usuário existente zera gamification e redireciona."""
    fake = _usuario_fake(uid="u5", email="u5@dtx.aero", nome="Usuario Cinco")
    fake.update = lambda **kw: None
    with (
        patch(
            "app.models_usuario.Usuario.get_by_id", side_effect=_get_by_id_side_effect("u5", fake)
        ),
        patch("app.routes.usuarios.Usuario.invalidar_cache_supervisores_por_area"),
    ):
        r = client_logado_admin.post("/admin/usuarios/u5/reset-exp", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/usuarios" in (r.location or "")


def test_resetar_exp_usuario_nao_encontrado(client_logado_admin):
    """POST reset-exp de ID inexistente redireciona com erro."""
    admin = _admin_mock_para_flask_login()
    with patch(
        "app.models_usuario.Usuario.get_by_id",
        side_effect=lambda uid: None if uid == "nao" else admin,
    ):
        r = client_logado_admin.post("/admin/usuarios/nao/reset-exp", follow_redirects=False)
    assert r.status_code == 302
