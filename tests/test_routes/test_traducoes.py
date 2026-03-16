"""Testes das rotas de administração de traduções (/admin/traducoes). Requer perfil admin."""


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
