"""Testes para decoradores RBAC — requer_perfil, requer_supervisor_area, requer_solicitante."""

from unittest.mock import MagicMock, patch


def _usuario(perfil, autenticado=True, area="TI"):
    u = MagicMock()
    u.is_authenticated = autenticado
    u.perfil = perfil
    u.area = area
    u.email = f"{perfil}@test.com"
    return u


# ── requer_perfil ──────────────────────────────────────────────────────────────


def test_requer_perfil_bloqueia_nao_autenticado(app):
    from app.decoradores import requer_perfil

    @requer_perfil("admin")
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("qualquer", autenticado=False)),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "login" in resp.location.lower()


def test_requer_perfil_bloqueia_perfil_errado_solicitante(app):
    from app.decoradores import requer_perfil

    @requer_perfil("admin")
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("solicitante")),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302


def test_requer_perfil_supervisor_sem_acesso_vai_para_painel(app):
    from app.decoradores import requer_perfil

    @requer_perfil("admin")
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("supervisor")),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "painel" in resp.location


def test_requer_perfil_permite_perfil_correto(app):
    from app.decoradores import requer_perfil

    @requer_perfil("admin")
    def rota():
        return "sucesso"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("admin")),
    ):
        result = rota()
    assert result == "sucesso"


def test_requer_perfil_aceita_multiplos_perfis(app):
    from app.decoradores import requer_perfil

    @requer_perfil("supervisor", "admin")
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("supervisor")),
    ):
        result = rota()
    assert result == "ok"


def test_requer_perfil_aceita_lista_como_argumento(app):
    from app.decoradores import requer_perfil

    @requer_perfil(["supervisor", "admin"])
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("admin")),
    ):
        result = rota()
    assert result == "ok"


# ── requer_supervisor_area ────────────────────────────────────────────────────


def test_requer_supervisor_area_bloqueia_nao_autenticado(app):
    from app.decoradores import requer_supervisor_area

    @requer_supervisor_area
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("qualquer", autenticado=False)),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "login" in resp.location.lower()


def test_requer_supervisor_area_bloqueia_solicitante(app):
    from app.decoradores import requer_supervisor_area

    @requer_supervisor_area
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("solicitante")),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302


def test_requer_supervisor_area_api_bloqueia_solicitante_com_json_403(app):
    from app.decoradores import requer_supervisor_area

    @requer_supervisor_area
    def rota():
        return "ok"

    with (
        app.test_request_context("/api/restrita"),
        patch("app.decoradores.current_user", _usuario("solicitante")),
        patch("app.decoradores.flash_t") as mock_flash,
    ):
        resp, status = rota()

    assert status == 403
    assert resp.get_json()["sucesso"] is False
    assert resp.get_json()["erro"]
    mock_flash.assert_not_called()


def test_requer_supervisor_area_permite_supervisor(app):
    from app.decoradores import requer_supervisor_area

    @requer_supervisor_area
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("supervisor")),
    ):
        result = rota()
    assert result == "ok"


def test_requer_supervisor_area_permite_admin(app):
    from app.decoradores import requer_supervisor_area

    @requer_supervisor_area
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("admin")),
    ):
        result = rota()
    assert result == "ok"


# ── requer_supervisor_area_ou_gestor_setor ──────────────────────────────────────


def _usuario_gestor_setor(perfil="solicitante", autenticado=True):
    """gestor_setor "puro" — sem perfil supervisor, só nivel_gestao."""
    u = _usuario(perfil, autenticado=autenticado)
    u.nivel_gestao = "gestor_setor"
    return u


def test_requer_supervisor_area_ou_gestor_setor_bloqueia_nao_autenticado(app):
    from app.decoradores import requer_supervisor_area_ou_gestor_setor

    @requer_supervisor_area_ou_gestor_setor
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("qualquer", autenticado=False)),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "login" in resp.location.lower()


def test_requer_supervisor_area_ou_gestor_setor_bloqueia_solicitante_comum(app):
    """Solicitante sem nivel_gestao continua bloqueado."""
    from app.decoradores import requer_supervisor_area_ou_gestor_setor

    @requer_supervisor_area_ou_gestor_setor
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("solicitante")),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302


def test_requer_supervisor_area_ou_gestor_setor_bloqueia_gerente_producao(app):
    """gerente_producao (company-wide) não entra nesta exceção — só gestor_setor."""
    from app.decoradores import requer_supervisor_area_ou_gestor_setor

    @requer_supervisor_area_ou_gestor_setor
    def rota():
        return "ok"

    u = _usuario("solicitante")
    u.nivel_gestao = "gerente_producao"
    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", u),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302


def test_requer_supervisor_area_ou_gestor_setor_permite_gestor_setor_puro(app):
    """gestor_setor "puro" (perfil solicitante, sem supervisor) passa pelo decorador."""
    from app.decoradores import requer_supervisor_area_ou_gestor_setor

    @requer_supervisor_area_ou_gestor_setor
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario_gestor_setor()),
    ):
        result = rota()
    assert result == "ok"


def test_requer_supervisor_area_ou_gestor_setor_permite_supervisor(app):
    from app.decoradores import requer_supervisor_area_ou_gestor_setor

    @requer_supervisor_area_ou_gestor_setor
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("supervisor")),
    ):
        result = rota()
    assert result == "ok"


def test_requer_supervisor_area_ou_gestor_setor_permite_admin(app):
    from app.decoradores import requer_supervisor_area_ou_gestor_setor

    @requer_supervisor_area_ou_gestor_setor
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("admin")),
    ):
        result = rota()
    assert result == "ok"


# ── requer_solicitante ────────────────────────────────────────────────────────


def test_requer_solicitante_bloqueia_nao_autenticado(app):
    from app.decoradores import requer_solicitante

    @requer_solicitante
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("qualquer", autenticado=False)),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "login" in resp.location.lower()


def test_requer_solicitante_permite_solicitante(app):
    from app.decoradores import requer_solicitante

    @requer_solicitante
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("solicitante")),
    ):
        result = rota()
    assert result == "ok"


def test_requer_solicitante_permite_supervisor(app):
    from app.decoradores import requer_solicitante

    @requer_solicitante
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("supervisor")),
    ):
        result = rota()
    assert result == "ok"


def test_requer_solicitante_permite_admin(app):
    from app.decoradores import requer_solicitante

    @requer_solicitante
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("admin")),
    ):
        result = rota()
    assert result == "ok"


def test_requer_solicitante_bloqueia_perfil_invalido(app):
    from app.decoradores import requer_solicitante

    @requer_solicitante
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("visitante")),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302


# ── requer_gestor ─────────────────────────────────────────────────────────────


def test_requer_gestor_bloqueia_nao_autenticado(app):
    from app.decoradores import requer_gestor

    @requer_gestor
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("qualquer", autenticado=False)),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "login" in resp.location.lower()


def test_requer_gestor_bloqueia_sem_nivel_gestao_solicitante(app):
    from app.decoradores import requer_gestor

    u = _usuario("solicitante")
    u.is_gestor = False

    @requer_gestor
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", u),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302


def test_requer_gestor_permite_is_gestor_true(app):
    from app.decoradores import requer_gestor

    u = _usuario("supervisor")
    u.is_gestor = True

    @requer_gestor
    def rota():
        return "gestor_ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", u),
    ):
        result = rota()
    assert result == "gestor_ok"


# ── requer_gestor_ou_admin — caminho não autenticado ─────────────────────────


def test_requer_gestor_ou_admin_bloqueia_nao_autenticado(app):
    from app.decoradores import requer_gestor_ou_admin

    @requer_gestor_ou_admin
    def rota():
        return "ok"

    with (
        app.test_request_context("/"),
        patch("app.decoradores.current_user", _usuario("qualquer", autenticado=False)),
        patch("app.decoradores.flash_t"),
    ):
        resp = rota()
    assert resp.status_code == 302
    assert "login" in resp.location.lower()
