"""Testes das rotas de administração de categorias (/admin/categorias). Requer perfil admin."""

from unittest.mock import patch


def test_admin_categorias_sem_login_redireciona(client):
    """GET /admin/categorias sem login redireciona para /login."""
    r = client.get("/admin/categorias", follow_redirects=False)
    assert r.status_code == 302
    assert "login" in r.location


def test_admin_categorias_com_solicitante_nao_acessa(client_logado_solicitante):
    """GET /admin/categorias com perfil solicitante não acessa: 403 ou 302 (ex.: redirect troca de senha)."""
    r = client_logado_solicitante.get("/admin/categorias", follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert "/admin/categorias" not in (r.location or "")


def test_admin_categorias_com_admin_retorna_200(client_logado_admin):
    """GET /admin/categorias com admin retorna 200 e página de categorias."""
    with (
        patch("app.routes.categorias.CategoriaSetor.get_all", return_value=[]),
        patch("app.routes.categorias.CategoriaGate.get_all", return_value=[]),
        patch("app.routes.categorias.CategoriaImpacto.get_all", return_value=[]),
    ):
        r = client_logado_admin.get("/admin/categorias", follow_redirects=False)
    assert r.status_code == 200
    assert (
        b"categorias" in r.data.lower() or b"setor" in r.data.lower() or b"gate" in r.data.lower()
    )
