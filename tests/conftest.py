"""Configuração pytest e fixtures compartilhadas."""
import os
import pytest

# Garante que o app seja importável
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
