"""Testes das rotas de administração de traduções (/admin/traducoes). Requer perfil admin."""

from unittest.mock import patch


def test_admin_traducoes_sem_login_redireciona(client):
    """GET /admin/traducoes sem login redireciona para /login."""
    r = client.get("/admin/traducoes", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_admin_traducoes_com_solicitante_nao_acessa(client_logado_solicitante):
    """GET /admin/traducoes com perfil solicitante não acessa: 403 ou 302 (ex.: redirect troca de senha)."""
    r = client_logado_solicitante.get("/admin/traducoes", follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert "/admin/traducoes" not in (r.location or "")


def test_admin_traducoes_com_admin_retorna_200(client_logado_admin):
    """GET /admin/traducoes com admin retorna 200."""
    r = client_logado_admin.get("/admin/traducoes", follow_redirects=False)
    assert r.status_code == 200
    assert b"tradu" in r.data.lower() or b"translation" in r.data.lower()


def test_admin_traducoes_get_excecao_redireciona_para_admin(client_logado_admin):
    """GET /admin/traducoes quando get_translations_dict lança exceção redireciona para /admin."""
    # A função usa inline import: `from app.i18n import get_translations_dict`
    with patch("app.i18n.get_translations_dict", side_effect=Exception("err")):
        r = client_logado_admin.get("/admin/traducoes", follow_redirects=False)
    assert r.status_code == 302


def test_admin_traducoes_post_sem_chave_redireciona(client_logado_admin):
    """POST /admin/traducoes sem chave redireciona com erro."""
    with patch("app.i18n.get_translations_dict", return_value={}):
        r = client_logado_admin.post(
            "/admin/traducoes",
            data={"chave": "", "pt_BR": "val", "en": "val", "es": "val"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_admin_traducoes_post_salva_nova_traducao(client_logado_admin):
    """POST /admin/traducoes com chave e valores salva e redireciona."""
    with (
        patch("app.i18n.get_translations_dict", return_value={}),
        patch("app.i18n.save_translations_dict", return_value=True),
    ):
        r = client_logado_admin.post(
            "/admin/traducoes",
            data={"chave": "nova_chave", "pt_BR": "Novo Valor", "en": "New Value", "es": "Nuevo"},
            follow_redirects=False,
        )
    assert r.status_code == 302
    assert "/admin/traducoes" in (r.location or "")


def test_admin_traducoes_post_erro_ao_salvar_redireciona(client_logado_admin):
    """POST /admin/traducoes quando save retorna False redireciona com erro."""
    with (
        patch("app.i18n.get_translations_dict", return_value={}),
        patch("app.i18n.save_translations_dict", return_value=False),
    ):
        r = client_logado_admin.post(
            "/admin/traducoes",
            data={"chave": "chave_x", "pt_BR": "v", "en": "v", "es": "v"},
            follow_redirects=False,
        )
    assert r.status_code == 302


def test_admin_traducoes_post_ajax_retorna_json_sucesso(client_logado_admin):
    """POST AJAX /admin/traducoes retorna JSON {sucesso: true} com status 200."""
    with (
        patch("app.i18n.get_translations_dict", return_value={}),
        patch("app.i18n.save_translations_dict", return_value=True),
    ):
        r = client_logado_admin.post(
            "/admin/traducoes",
            data={"chave": "ajax_key", "pt_BR": "v", "en": "v", "es": "v"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=False,
        )
    assert r.status_code == 200
    json_data = r.get_json()
    assert json_data is not None
    assert json_data.get("sucesso") is True


def test_admin_traducoes_post_ajax_erro_retorna_json_500(client_logado_admin):
    """POST AJAX /admin/traducoes quando save falha retorna JSON {sucesso: false} e 500."""
    with (
        patch("app.i18n.get_translations_dict", return_value={}),
        patch("app.i18n.save_translations_dict", return_value=False),
    ):
        r = client_logado_admin.post(
            "/admin/traducoes",
            data={"chave": "ajax_key", "pt_BR": "v", "en": "v", "es": "v"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            follow_redirects=False,
        )
    assert r.status_code == 500
    json_data = r.get_json()
    assert json_data is not None
    assert json_data.get("sucesso") is False
