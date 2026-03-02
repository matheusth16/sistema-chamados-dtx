"""Testes das rotas de administração de usuários (/admin/usuarios). Requer perfil admin."""

from unittest.mock import patch, MagicMock


def test_admin_usuarios_sem_login_redireciona_para_login(client):
    """GET /admin/usuarios sem estar logado redireciona para /login."""
    r = client.get('/admin/usuarios', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location


def test_admin_usuarios_com_solicitante_nao_acessa(client_logado_solicitante):
    """GET /admin/usuarios com perfil solicitante não acessa: 403 ou 302 (ex.: redirect troca de senha)."""
    r = client_logado_solicitante.get('/admin/usuarios', follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert '/admin/usuarios' not in (r.location or '')


def test_admin_usuarios_com_supervisor_nao_acessa(client_logado_supervisor):
    """GET /admin/usuarios com perfil supervisor não acessa: 403 ou 302."""
    r = client_logado_supervisor.get('/admin/usuarios', follow_redirects=False)
    assert r.status_code in (403, 302)
    if r.status_code == 302:
        assert '/admin/usuarios' not in (r.location or '')


def test_admin_usuarios_com_admin_retorna_200(client_logado_admin):
    """GET /admin/usuarios com perfil admin retorna 200 e página de usuários."""
    with patch('app.routes.usuarios.Usuario.get_all') as mock_get_all:
        mock_get_all.return_value = []
        r = client_logado_admin.get('/admin/usuarios', follow_redirects=False)
    assert r.status_code == 200
    assert b'usuarios' in r.data.lower() or b'user' in r.data.lower()


def test_admin_usuarios_novo_sem_login_redireciona(client):
    """GET /admin/usuarios/novo sem login redireciona para login."""
    r = client.get('/admin/usuarios/novo', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location


def test_admin_usuarios_novo_com_admin_retorna_200(client_logado_admin):
    """GET /admin/usuarios/novo com admin retorna formulário."""
    r = client_logado_admin.get('/admin/usuarios/novo', follow_redirects=False)
    assert r.status_code == 200
