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


def test_requer_perfil_supervisor_sem_acesso_vai_para_admin_page(app):
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
    assert "admin" in resp.location


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
