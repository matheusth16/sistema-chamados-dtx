"""Testes das rotas de chamados (formulário e criação)."""


def test_formulario_sem_login_redireciona_para_login(client):
    """GET / (formulário) sem autenticação redireciona para login."""
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location
