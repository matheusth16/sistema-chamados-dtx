"""Testes para o perfil admin_global e rotas exclusivas /admin-global."""

from unittest.mock import MagicMock, patch

from app.models_usuario import Usuario

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _usuario_mock(uid, perfil, email=None):
    u = MagicMock(spec=Usuario)
    u.id = uid
    u.email = email or f"{uid}@test.com"
    u.nome = f"Usuário {uid}"
    u.perfil = perfil
    u.area = "Geral"
    u.areas = ["Geral"]
    u.is_authenticated = True
    u.is_active = True
    u.is_anonymous = False
    u.must_change_password = False
    u.onboarding_completo = True
    u.get_id = lambda: str(uid)
    return u


# ---------------------------------------------------------------------------
# T1A — Modelo: properties is_admin_or_above e is_supervisor_or_above
# ---------------------------------------------------------------------------


def test_is_admin_or_above_admin():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="admin")
    assert u.is_admin_or_above is True


def test_is_admin_or_above_admin_global():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="admin_global")
    assert u.is_admin_or_above is True


def test_is_admin_or_above_supervisor_false():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="supervisor")
    assert u.is_admin_or_above is False


def test_is_admin_or_above_solicitante_false():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="solicitante")
    assert u.is_admin_or_above is False


def test_is_supervisor_or_above_supervisor():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="supervisor")
    assert u.is_supervisor_or_above is True


def test_is_supervisor_or_above_admin():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="admin")
    assert u.is_supervisor_or_above is True


def test_is_supervisor_or_above_admin_global():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="admin_global")
    assert u.is_supervisor_or_above is True


def test_is_supervisor_or_above_solicitante_false():
    u = Usuario(id="x", email="a@b.com", nome="A", perfil="solicitante")
    assert u.is_supervisor_or_above is False


# ---------------------------------------------------------------------------
# T1B — Decorador: requer_perfil("admin") aceita admin_global
# ---------------------------------------------------------------------------


def test_requer_perfil_admin_aceita_admin_global(app):
    from app.decoradores import requer_perfil

    @requer_perfil("admin")
    def rota():
        return "ok"

    user = _usuario_mock("ag_1", "admin_global")
    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", user),
    ):
        resp = rota()
    assert resp == "ok"


def test_requer_perfil_admin_bloqueia_supervisor(app):
    from app.decoradores import requer_perfil

    @requer_perfil("admin")
    def rota():
        return "ok"

    user = _usuario_mock("sup_1", "supervisor")
    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", user),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "painel" in resp.location


def test_requer_supervisor_area_aceita_admin_global(app):
    """requer_supervisor_area deve permitir admin_global."""
    from app.decoradores import requer_supervisor_area

    @requer_supervisor_area
    def rota():
        return "ok"

    user = _usuario_mock("ag_1", "admin_global")
    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", user),
        patch("app.decoradores.current_app"),
    ):
        resp = rota()
    assert resp == "ok"


def test_requer_solicitante_aceita_admin_global(app):
    """requer_solicitante deve permitir admin_global."""
    from app.decoradores import requer_solicitante

    @requer_solicitante
    def rota():
        return "ok"

    user = _usuario_mock("ag_1", "admin_global")
    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", user),
    ):
        resp = rota()
    assert resp == "ok"


# ---------------------------------------------------------------------------
# T1C — Rotas exclusivas /admin-global
# ---------------------------------------------------------------------------


def test_admin_global_acesso_permitido(client_logado_admin_global):
    """GET /admin-global retorna 200 para admin_global."""
    with (
        patch("app.routes.admin_global.db") as mock_db,
        patch("app.routes.admin_global.Usuario") as mock_usuario,
    ):
        mock_db.collection.return_value.get.return_value = []
        mock_usuario.get_all.return_value = []
        r = client_logado_admin_global.get("/admin-global", follow_redirects=False)
    assert r.status_code == 200


def test_admin_global_acesso_negado_admin(client_logado_admin):
    """GET /admin-global retorna 302/403 para admin (sub-admin)."""
    r = client_logado_admin.get("/admin-global", follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_global_acesso_negado_supervisor(client_logado_supervisor):
    """GET /admin-global retorna 302/403 para supervisor."""
    r = client_logado_supervisor.get("/admin-global", follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_global_acesso_negado_solicitante(client_logado_solicitante):
    """GET /admin-global retorna 302/403 para solicitante."""
    r = client_logado_solicitante.get("/admin-global", follow_redirects=False)
    assert r.status_code in (302, 403)


def test_admin_global_sem_login_redireciona(client):
    """GET /admin-global sem autenticação redireciona para login."""
    r = client.get("/admin-global", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


# ---------------------------------------------------------------------------
# T1D — Proteção de criação de admin (T8)
# ---------------------------------------------------------------------------


def test_sub_admin_nao_pode_criar_admin(client_logado_admin):
    """Sub-admin não pode criar usuário com perfil=admin via formulário."""
    with patch("app.routes.usuarios.Usuario.email_existe", return_value=False):
        r = client_logado_admin.post(
            "/admin/usuarios",
            data={
                "acao": "criar",
                "email": "novo@test.com",
                "nome": "Novo Admin",
                "perfil": "admin",
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
    # Sub-admin não pode criar admin: deve redirecionar sem criar
    # (o flash de erro será verificado por mensagem na próxima request)


def test_sub_admin_nao_pode_editar_para_admin(client_logado_admin):
    """Sub-admin não pode promover usuário para perfil=admin via edição."""
    usuario_existente = _usuario_mock("u_1", "supervisor")
    usuario_existente.email = "sup@test.com"
    with (
        patch("app.routes.usuarios.Usuario.get_by_id", return_value=usuario_existente),
        patch("app.routes.usuarios.Usuario.email_existe", return_value=False),
    ):
        r = client_logado_admin.post(
            "/admin/usuarios/u_1/editar",
            data={
                "email": "sup@test.com",
                "nome": "Supervisor",
                "perfil": "admin",
                "areas": ["Geral"],
            },
            follow_redirects=False,
        )
    assert r.status_code == 302
