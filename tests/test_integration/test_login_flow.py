"""Testes de integração: fluxo de login e redirecionamento."""
import pytest
from unittest.mock import patch, MagicMock


def test_login_get_exibe_formulario(client):
    """GET /login exibe página de login."""
    r = client.get('/login')
    assert r.status_code == 200
    assert b'email' in r.data.lower() or b'login' in r.data.lower()


def test_login_post_credenciais_invalidas_volta_para_login(client):
    """POST /login com email/senha inválidos redireciona para login com flash."""
    r = client.post('/login', data={'email': 'invalido@test.com', 'senha': 'wrong'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'login' in r.data.lower() or b'incorretos' in r.data.lower() or b'email' in r.data.lower()


def test_login_post_sucesso_redireciona_conforme_perfil(client):
    """POST /login com credenciais válidas redireciona (solicitante -> /, supervisor/admin -> /admin)."""
    usuario = MagicMock()
    usuario.id = 'user_1'
    usuario.email = 'sol@test.com'
    usuario.nome = 'Solicitante'
    usuario.perfil = 'solicitante'
    usuario.area = 'Planejamento'
    usuario.check_password = MagicMock(return_value=True)
    with patch('app.routes.auth.Usuario.get_by_email', return_value=usuario):
        r = client.post('/login', data={'email': 'sol@test.com', 'senha': 'ok'}, follow_redirects=False)
    assert r.status_code == 302
    assert '/' in r.location and 'admin' not in r.location or r.location.endswith('/')

    usuario.perfil = 'supervisor'
    with patch('app.routes.auth.Usuario.get_by_email', return_value=usuario):
        r2 = client.post('/login', data={'email': 'sup@test.com', 'senha': 'ok'}, follow_redirects=False)
    assert r2.status_code == 302
    assert 'admin' in r2.location


def test_acesso_admin_sem_login_redireciona_para_login(client):
    """GET /admin sem autenticação redireciona para login."""
    r = client.get('/admin', follow_redirects=False)
    assert r.status_code == 302
    assert 'login' in r.location
