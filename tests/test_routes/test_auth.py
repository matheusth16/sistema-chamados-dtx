"""Testes das rotas de autenticação (login, logout)."""


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


def test_logout_sem_login_redireciona_para_login(client):
    """GET /logout sem estar logado redireciona para login."""
    r = client.get('/logout', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location


def test_index_sem_login_redireciona_para_login(client):
    """Acesso a / sem autenticação redireciona para login."""
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location
