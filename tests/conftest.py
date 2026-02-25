"""Configuração pytest e fixtures compartilhadas."""
import os
import pytest
from unittest.mock import patch, MagicMock

# Garante que o app seja importável (FLASK_ENV=testing evita exigência de SECRET_KEY de produção)
os.environ.setdefault('FLASK_ENV', 'testing')


@pytest.fixture
def app():
    """Cria aplicação Flask para testes."""
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret'
    return app


@pytest.fixture
def client(app):
    """Cliente de teste para requisições HTTP."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Runner para comandos CLI."""
    return app.test_cli_runner()


def _usuario_mock(uid, email, nome, perfil, area='Geral', areas=None):
    """Cria um MagicMock de usuário para testes.
    area: string única (usado como u.area e, se areas não for passado, como u.areas = [area]).
    areas: lista de áreas (usado por permissions: supervisor vê só chamados cuja área está em user.areas).
    """
    u = MagicMock()
    u.id = uid
    u.email = email
    u.nome = nome
    u.perfil = perfil
    u.area = area
    u.areas = areas if areas is not None else ([area] if isinstance(area, str) else area)
    u.is_authenticated = True
    u.check_password = MagicMock(return_value=True)
    # Flask-Login serializa user_id na sessão; get_id deve retornar string
    u.get_id = lambda: str(uid)
    return u


@pytest.fixture
def client_logado_solicitante(client, app):
    """Cliente com usuário solicitante já logado. Use em testes que precisam de sessão ativa."""
    user = _usuario_mock('sol_1', 'sol@test.com', 'Solicitante Teste', 'solicitante', 'Planejamento')
    with patch('app.routes.auth.Usuario.get_by_email', return_value=user):
        with patch('app.models_usuario.Usuario.get_by_id', return_value=user):
            client.post('/login', data={'email': 'sol@test.com', 'senha': 'ok'}, follow_redirects=False)
            yield client


@pytest.fixture
def client_logado_supervisor(client, app):
    """Cliente com usuário supervisor já logado."""
    user = _usuario_mock('sup_1', 'sup@test.com', 'Supervisor Teste', 'supervisor', 'Manutencao')
    with patch('app.routes.auth.Usuario.get_by_email', return_value=user):
        with patch('app.models_usuario.Usuario.get_by_id', return_value=user):
            client.post('/login', data={'email': 'sup@test.com', 'senha': 'ok'}, follow_redirects=False)
            yield client


@pytest.fixture
def client_logado_admin(client, app):
    """Cliente com usuário admin já logado."""
    user = _usuario_mock('admin_1', 'admin@test.com', 'Admin Teste', 'admin', 'Geral')
    with patch('app.routes.auth.Usuario.get_by_email', return_value=user):
        with patch('app.models_usuario.Usuario.get_by_id', return_value=user):
            client.post('/login', data={'email': 'admin@test.com', 'senha': 'ok'}, follow_redirects=False)
            yield client


@pytest.fixture
def mock_firestore():
    """
    Mock do Firestore para testes que não devem acessar o banco real.
    Use: def test_x(mock_firestore): ... (o mock está em app.database.db).
    """
    with patch('app.database.db', MagicMock()) as mock_db:
        yield mock_db
