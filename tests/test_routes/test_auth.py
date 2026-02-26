"""Testes das rotas de autenticação (login, logout). Ref: CT-AUTH-*."""

from unittest.mock import patch, MagicMock


def test_login_get_retorna_200(client):
    """GET /login retorna 200 e página de login."""
    r = client.get('/login')
    assert r.status_code == 200
    assert b'login' in r.data.lower() or b'email' in r.data.lower() or b'Email' in r.data


def test_login_post_sem_credenciais_redireciona_com_flash(client):
    """POST /login sem email/senha redireciona para login."""
    r = client.post('/login', data={}, follow_redirects=False)
    assert r.status_code in (302, 200)
    if r.status_code == 302:
        assert '/login' in r.location


def test_login_post_email_senha_vazios_permanece_em_login(client):
    """CT-AUTH-03: POST /login com email ou senha vazios permanece na página de login com mensagem."""
    r = client.post('/login', data={'email': '', 'senha': 'qualquer'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'login' in r.data.lower() or b'email' in r.data.lower()

    r2 = client.post('/login', data={'email': 'user@test.com', 'senha': ''}, follow_redirects=True)
    assert r2.status_code == 200
    assert b'login' in r2.data.lower() or b'email' in r2.data.lower()


def test_login_post_credenciais_invalidas_nao_redireciona_para_index(client):
    """CT-AUTH-04: POST /login com email/senha incorretos não cria sessão; permanece em login."""
    with patch('app.routes.auth.Usuario.get_by_email', return_value=None):
        r = client.post('/login', data={'email': 'naoexiste@test.com', 'senha': '123'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'login' in r.data.lower() or b'email' in r.data.lower()

    usuario = MagicMock()
    usuario.check_password = MagicMock(return_value=False)
    with patch('app.routes.auth.Usuario.get_by_email', return_value=usuario):
        r2 = client.post('/login', data={'email': 'existente@test.com', 'senha': 'errada'}, follow_redirects=True)
    assert r2.status_code == 200
    assert b'login' in r2.data.lower() or b'email' in r2.data.lower() or b'incorretos' in r2.data.lower()


def test_logout_com_usuario_logado_redireciona_para_login(client_logado_solicitante):
    """CT-AUTH-05: GET /logout com usuário logado encerra sessão e redireciona para /login."""
    r = client_logado_solicitante.get('/logout', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location

    # Após logout, acesso a rota protegida deve redirecionar para login
    r2 = client_logado_solicitante.get('/', follow_redirects=False)
    assert r2.status_code == 302
    assert 'login' in r2.location


def test_logout_sem_login_redireciona_para_login(client):
    """GET /logout sem estar logado redireciona para login."""
    r = client.get('/logout', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location


def test_index_sem_login_redireciona_para_login(client):
    """CT-AUTH-06: Acesso a / sem autenticação redireciona para login."""
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location
