"""
Fixtures compartilhadas para testes E2E.

Uso:
    pytest tests/e2e --base-url http://127.0.0.1:5000

Variáveis de ambiente esperadas (para testes que fazem login):
    TEST_SOLICITANTE_EMAIL  / TEST_SOLICITANTE_PASSWORD
    TEST_SUPERVISOR_EMAIL   / TEST_SUPERVISOR_PASSWORD
    TEST_ADMIN_EMAIL        / TEST_ADMIN_PASSWORD

Exemplo de .env.test:
    TEST_SOLICITANTE_EMAIL=sol@dtx.com
    TEST_SOLICITANTE_PASSWORD=senha123
    TEST_SUPERVISOR_EMAIL=sup@dtx.com
    TEST_SUPERVISOR_PASSWORD=senha123
    TEST_ADMIN_EMAIL=admin@dtx.com
    TEST_ADMIN_PASSWORD=senha123
"""

import os

import pytest
from playwright.sync_api import Page

# ---------------------------------------------------------------------------
# Configuração de base_url
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """Registra o marker e2e para evitar warnings."""
    config.addinivalue_line("markers", "e2e: testes end-to-end contra servidor ativo")


@pytest.fixture(scope="session")
def base_url() -> str:
    """URL base do servidor Flask. Pode ser sobrescrita via --base-url ou FLASK_TEST_URL."""
    return os.environ.get("FLASK_TEST_URL", "http://127.0.0.1:5000")


# ---------------------------------------------------------------------------
# Credenciais de teste (de variáveis de ambiente)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def creds_solicitante() -> dict:
    return {
        "email": os.environ.get("TEST_SOLICITANTE_EMAIL", ""),
        "password": os.environ.get("TEST_SOLICITANTE_PASSWORD", ""),
    }


@pytest.fixture(scope="session")
def creds_supervisor() -> dict:
    return {
        "email": os.environ.get("TEST_SUPERVISOR_EMAIL", ""),
        "password": os.environ.get("TEST_SUPERVISOR_PASSWORD", ""),
    }


@pytest.fixture(scope="session")
def creds_admin() -> dict:
    return {
        "email": os.environ.get("TEST_ADMIN_EMAIL", ""),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", ""),
    }


# ---------------------------------------------------------------------------
# Configuração do Playwright
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configuração padrão do contexto de browser para todos os testes E2E."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "pt-BR",
    }


# ---------------------------------------------------------------------------
# Helpers de autenticação
# ---------------------------------------------------------------------------


def _do_login(page: Page, base_url: str, email: str, password: str) -> None:
    """Realiza login na aplicação via UI."""
    page.goto(f"{base_url}/login")
    page.get_by_test_id("email-input").fill(email)
    page.get_by_test_id("password-input").fill(password)
    page.get_by_test_id("login-submit-btn").click()
    # Aguarda que o splash sum e a navegação complete
    page.wait_for_load_state("networkidle")


@pytest.fixture
def logged_in_solicitante(page: Page, base_url: str, creds_solicitante: dict):
    """Page já autenticada como solicitante."""
    if not creds_solicitante["email"]:
        pytest.skip("TEST_SOLICITANTE_EMAIL não configurado")
    _do_login(page, base_url, creds_solicitante["email"], creds_solicitante["password"])
    return page


@pytest.fixture
def logged_in_supervisor(page: Page, base_url: str, creds_supervisor: dict):
    """Page já autenticada como supervisor."""
    if not creds_supervisor["email"]:
        pytest.skip("TEST_SUPERVISOR_EMAIL não configurado")
    _do_login(page, base_url, creds_supervisor["email"], creds_supervisor["password"])
    return page


@pytest.fixture
def logged_in_admin(page: Page, base_url: str, creds_admin: dict):
    """Page já autenticada como admin."""
    if not creds_admin["email"]:
        pytest.skip("TEST_ADMIN_EMAIL não configurado")
    _do_login(page, base_url, creds_admin["email"], creds_admin["password"])
    return page
