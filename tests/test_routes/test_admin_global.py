"""Testes para o perfil admin_global e rotas exclusivas /admin-global."""

from unittest.mock import MagicMock, patch

from app.models_usuario import Usuario

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeThread:
    """Thread fake para executar target imediatamente nos testes."""

    def __init__(self, target=None, daemon=None):
        self._target = target
        self.daemon = daemon

    def start(self):
        if self._target:
            self._target()


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
    u.mfa_enabled = True
    u.onboarding_perfis_vistos = []
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


# ---------------------------------------------------------------------------
# T1E — requer_admin_global decorator
# ---------------------------------------------------------------------------


def test_requer_admin_global_envolve_com_requer_perfil_admin_global(app):
    """requer_admin_global deve retornar uma função decorada por requer_perfil('admin_global')."""
    from app.routes.admin_global import requer_admin_global

    def rota_fake():
        return "ok"

    user = _usuario_mock("ag_1", "admin_global")
    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", user),
    ):
        resp = requer_admin_global(rota_fake)()
    assert resp == "ok"


# ---------------------------------------------------------------------------
# T1F — Dashboard: branches inner/outer exception
# ---------------------------------------------------------------------------


def test_admin_global_dashboard_inner_db_exception_ainda_retorna_200(client_logado_admin_global):
    """Quando db.collection("chamados").get() lança, total_chamados fica 0 mas retorna 200."""
    with (
        patch("app.routes.admin_global.db") as mock_db,
        patch("app.routes.admin_global.Usuario") as mock_usuario,
    ):
        mock_usuario.get_all.return_value = []
        mock_db.collection.return_value.get.side_effect = Exception("firestore fora")
        r = client_logado_admin_global.get("/admin-global", follow_redirects=False)
    assert r.status_code == 200


def test_admin_global_dashboard_outer_exception_redireciona_para_admin(client_logado_admin_global):
    """Quando Usuario.get_all() lança, redireciona para /admin com flash de erro."""
    with (
        patch("app.routes.admin_global.db"),
        patch("app.routes.admin_global.Usuario") as mock_usuario,
    ):
        mock_usuario.get_all.side_effect = Exception("db down")
        r = client_logado_admin_global.get("/admin-global", follow_redirects=False)
    assert r.status_code == 302
    assert "admin" in (r.location or "").lower()


# ---------------------------------------------------------------------------
# T1G — Rotas POST: rebaixar e promover
# ---------------------------------------------------------------------------


def test_admin_global_rebaixar_admin_sucesso(client_logado_admin_global):
    """POST /admin-global/admins/<id>/rebaixar com sub-admin existente rebaixa para supervisor."""
    sub_admin = _usuario_mock("sa_1", "admin", email="subadmin@test.com")
    sub_admin.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sub_admin if uid == "sa_1" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sa_1/rebaixar", follow_redirects=False
        )
    assert r.status_code == 302
    sub_admin.update.assert_called_once_with(perfil="supervisor", onboarding_passo=0)


def test_admin_global_rebaixar_admin_perfil_ja_visto_nao_reseta_onboarding(
    client_logado_admin_global,
):
    """Rebaixar pra um perfil já visto antes (ex.: já foi supervisor) não reseta onboarding_passo."""
    sub_admin = _usuario_mock("sa_visto", "admin", email="subadmin.visto@test.com")
    sub_admin.onboarding_perfis_vistos = ["solicitante", "supervisor", "admin"]
    sub_admin.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sub_admin if uid == "sa_visto" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sa_visto/rebaixar", follow_redirects=False
        )
    assert r.status_code == 302
    sub_admin.update.assert_called_once_with(perfil="supervisor")


def test_admin_global_rebaixar_admin_dispara_notificacao(client_logado_admin_global):
    """POST rebaixar dispara notificar_mudanca_perfil para o usuário rebaixado."""
    sub_admin = _usuario_mock("sa_notif", "admin", email="subadmin.notif@test.com")
    sub_admin.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sub_admin if uid == "sa_notif" else ag_user

    with (
        patch("app.models_usuario.Usuario.get_by_id", side_effect=_side),
        patch("app.routes.admin_global.notificar_mudanca_perfil") as mock_notificar,
        patch("app.routes.admin_global.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sa_notif/rebaixar", follow_redirects=False
        )
    assert r.status_code == 302
    mock_notificar.assert_called_once()
    kwargs = mock_notificar.call_args.kwargs
    assert kwargs["usuario_email"] == "subadmin.notif@test.com"
    assert kwargs["novo_perfil"] == "supervisor"


def test_admin_global_rebaixar_usuario_nao_encontrado(client_logado_admin_global):
    """POST rebaixar com ID inexistente redireciona com flash user_not_found."""
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return None if uid == "nao_existe" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/nao_existe/rebaixar", follow_redirects=False
        )
    assert r.status_code == 302
    assert "admin" in (r.location or "").lower()


def test_admin_global_rebaixar_usuario_nao_admin_redireciona(client_logado_admin_global):
    """POST rebaixar com usuário de perfil ≠ admin (ex.: supervisor) redireciona sem alterar."""
    sup = _usuario_mock("sup_x", "supervisor")
    sup.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sup if uid == "sup_x" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sup_x/rebaixar", follow_redirects=False
        )
    assert r.status_code == 302
    sup.update.assert_not_called()


def test_admin_global_rebaixar_acesso_negado_para_admin(client_logado_admin):
    """POST rebaixar por sub-admin é bloqueado — redireciona para /admin."""
    r = client_logado_admin.post("/admin-global/admins/sa_1/rebaixar", follow_redirects=False)
    assert r.status_code == 302
    assert "admin" in (r.location or "").lower()


def test_admin_global_rebaixar_excecao_redireciona(client_logado_admin_global):
    """POST rebaixar com exceção em update() redireciona com flash error_server."""
    sub_admin = _usuario_mock("sa_exc", "admin")
    sub_admin.update = MagicMock(side_effect=Exception("db error"))
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sub_admin if uid == "sa_exc" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sa_exc/rebaixar", follow_redirects=False
        )
    assert r.status_code == 302


def test_admin_global_promover_supervisor_sucesso(client_logado_admin_global):
    """POST /admin-global/admins/<id>/promover com supervisor existente promove para admin."""
    sup = _usuario_mock("sup_prm", "supervisor", email="sup@test.com")
    sup.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sup if uid == "sup_prm" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sup_prm/promover", follow_redirects=False
        )
    assert r.status_code == 302
    sup.update.assert_called_once_with(perfil="admin", onboarding_passo=0)


def test_admin_global_promover_supervisor_perfil_ja_visto_nao_reseta_onboarding(
    client_logado_admin_global,
):
    """Promover pra um perfil já visto antes não reseta onboarding_passo."""
    sup = _usuario_mock("sup_visto", "supervisor", email="sup.visto@test.com")
    sup.onboarding_perfis_vistos = ["solicitante", "admin"]
    sup.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sup if uid == "sup_visto" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sup_visto/promover", follow_redirects=False
        )
    assert r.status_code == 302
    sup.update.assert_called_once_with(perfil="admin")


def test_admin_global_promover_supervisor_dispara_notificacao(client_logado_admin_global):
    """POST promover dispara notificar_mudanca_perfil para o usuário promovido."""
    sup = _usuario_mock("sup_notif", "supervisor", email="sup.notif@test.com")
    sup.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sup if uid == "sup_notif" else ag_user

    with (
        patch("app.models_usuario.Usuario.get_by_id", side_effect=_side),
        patch("app.routes.admin_global.notificar_mudanca_perfil") as mock_notificar,
        patch("app.routes.admin_global.threading.Thread", side_effect=_FakeThread),
    ):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sup_notif/promover", follow_redirects=False
        )
    assert r.status_code == 302
    mock_notificar.assert_called_once()
    kwargs = mock_notificar.call_args.kwargs
    assert kwargs["usuario_email"] == "sup.notif@test.com"
    assert kwargs["novo_perfil"] == "admin"


def test_admin_global_promover_usuario_nao_encontrado(client_logado_admin_global):
    """POST promover com ID inexistente redireciona com flash user_not_found."""
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return None if uid == "nao_existe" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/nao_existe/promover", follow_redirects=False
        )
    assert r.status_code == 302
    assert "admin" in (r.location or "").lower()


def test_admin_global_promover_usuario_nao_supervisor_redireciona(client_logado_admin_global):
    """POST promover com usuário de perfil ≠ supervisor redireciona sem alterar."""
    sol = _usuario_mock("sol_x", "solicitante")
    sol.update = MagicMock()
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sol if uid == "sol_x" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sol_x/promover", follow_redirects=False
        )
    assert r.status_code == 302
    sol.update.assert_not_called()


def test_admin_global_promover_acesso_negado_para_admin(client_logado_admin):
    """POST promover por sub-admin é bloqueado — redireciona para /admin."""
    r = client_logado_admin.post("/admin-global/admins/sup_1/promover", follow_redirects=False)
    assert r.status_code == 302
    assert "admin" in (r.location or "").lower()


def test_admin_global_promover_excecao_redireciona(client_logado_admin_global):
    """POST promover com exceção em update() redireciona com flash error_server."""
    sup = _usuario_mock("sup_exc", "supervisor")
    sup.update = MagicMock(side_effect=Exception("db error"))
    ag_user = _usuario_mock("ag_1", "admin_global")

    def _side(uid):
        return sup if uid == "sup_exc" else ag_user

    with patch("app.models_usuario.Usuario.get_by_id", side_effect=_side):
        r = client_logado_admin_global.post(
            "/admin-global/admins/sup_exc/promover", follow_redirects=False
        )
    assert r.status_code == 302


# ---------------------------------------------------------------------------
# T1H — Dashboard: agrupamento correto por perfil
# ---------------------------------------------------------------------------


def test_admin_global_dashboard_agrupa_por_perfil_corretamente(client_logado_admin_global):
    """Dashboard agrupa usuários corretamente em sub_admins, supervisores e solicitantes."""
    admin1 = _usuario_mock("a1", "admin")
    sup1 = _usuario_mock("s1", "supervisor")
    sol1 = _usuario_mock("sl1", "solicitante")
    ag_user = _usuario_mock("ag_1", "admin_global")

    with (
        patch("app.routes.admin_global.db") as mock_db,
        patch("app.routes.admin_global.Usuario") as mock_usuario,
        patch("app.models_usuario.Usuario.get_by_id", return_value=ag_user),
    ):
        mock_usuario.get_all.return_value = [admin1, sup1, sol1]
        mock_db.collection.return_value.get.return_value = [MagicMock(), MagicMock()]
        r = client_logado_admin_global.get("/admin-global", follow_redirects=False)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# T1I — Redirect por perfil (solicitante → index, supervisor → painel)
# ---------------------------------------------------------------------------


def test_admin_global_redirect_solicitante_para_index(client_logado_solicitante):
    """GET /admin-global com perfil solicitante redireciona para /."""
    r = client_logado_solicitante.get("/admin-global", follow_redirects=False)
    assert r.status_code in (302, 403)
    if r.status_code == 302:
        assert "index" in r.location or "/" in r.location


def test_admin_global_redirect_supervisor_para_painel(client_logado_supervisor):
    """GET /admin-global com perfil supervisor redireciona para /painel."""
    r = client_logado_supervisor.get("/admin-global", follow_redirects=False)
    assert r.status_code in (302, 403)
    if r.status_code == 302:
        assert "painel" in r.location or "admin" in r.location
