"""
Fixtures compartilhadas para testes E2E.

Uso:
    pytest tests/e2e --base-url http://127.0.0.1:5000

Variáveis de ambiente esperadas (para testes que fazem login):
    TEST_SOLICITANTE_EMAIL  / TEST_SOLICITANTE_PASSWORD
    TEST_SUPERVISOR_EMAIL   / TEST_SUPERVISOR_PASSWORD
    TEST_ADMIN_EMAIL        / TEST_ADMIN_PASSWORD

Modo stub para CI (sem servidor externo):
    FLASK_E2E_STUB=1 pytest tests/e2e -m smoke
    (também ativa quando CI=true e FLASK_TEST_URL não estiver definido)

Exemplo de .env.test:
    TEST_SOLICITANTE_EMAIL=sol@dtx.com
    TEST_SOLICITANTE_PASSWORD=senha123
    TEST_SUPERVISOR_EMAIL=sup@dtx.com
    TEST_SUPERVISOR_PASSWORD=senha123
    TEST_ADMIN_EMAIL=admin@dtx.com
    TEST_ADMIN_PASSWORD=senha123
"""

import os
import threading
import urllib.error
import urllib.request
from collections.abc import Generator

import pytest
from playwright.sync_api import Page

DEFAULT_TIMEOUT = 10_000  # ms — tempo padrão de espera para assertions E2E


# ---------------------------------------------------------------------------
# Stub server para CI (sem Firebase real, sem servidor externo)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _stub_server() -> Generator[str | None, None, None]:
    """Inicia Flask em background para CI quando nenhum servidor externo está disponível.

    Ativado quando FLASK_E2E_STUB=1 ou CI=true e FLASK_TEST_URL não está definido.
    Retorna a URL base do servidor stub, ou None se o modo stub não estiver ativo.

    Smoke tests que não precisam de login (SMOKE-01, 02, 03) funcionam com o stub
    pois o Flask trata /login e o redirect de rotas protegidas sem acessar Firestore.
    Chamadas a Firestore que ocorrerem no stub são capturadas silenciosamente (try/except
    nos services retornam None) — o comportamento de "credenciais inválidas" é preservado.
    """
    ci_mode = (
        os.environ.get("CI") == "true" or os.environ.get("FLASK_E2E_STUB") == "1"
    ) and not os.environ.get("FLASK_TEST_URL")

    if not ci_mode:
        yield None
        return

    from werkzeug.serving import make_server

    from app import create_app

    stub = create_app()
    stub.config["TESTING"] = True
    stub.config["WTF_CSRF_ENABLED"] = False
    stub.config["SECRET_KEY"] = "test-stub-e2e-secret"
    stub.config["APP_BASE_URL"] = ""
    # Desativa rate limiting no stub para que SMOKE-02 (login inválido) não bloqueie
    stub.config["RATELIMIT_ENABLED"] = False

    # Porta 0 = OS escolhe uma porta livre (sem race condition)
    server = make_server("127.0.0.1", 0, stub)
    port = server.socket.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield url

    server.shutdown()


# ---------------------------------------------------------------------------
# Configuração de base_url
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """Registra os markers customizados para evitar warnings."""
    config.addinivalue_line("markers", "e2e: testes end-to-end contra servidor ativo")
    config.addinivalue_line(
        "markers",
        "capture: ferramenta de captura de screenshots (não é um teste de correção; "
        "não roda em CI/pytest normal, apenas quando explicitamente selecionada)",
    )


@pytest.fixture(scope="session")
def base_url(_stub_server: str | None) -> str:
    """URL base do servidor Flask.

    Prioridade:
    1. URL do stub server (quando FLASK_E2E_STUB=1 ou CI=true)
    2. FLASK_TEST_URL env var
    3. Padrão: http://127.0.0.1:5000
    """
    if _stub_server:
        return _stub_server
    return os.environ.get("FLASK_TEST_URL", "http://127.0.0.1:5000")


@pytest.fixture(scope="session", autouse=True)
def require_server(base_url: str) -> None:
    """Auto-skip da suíte inteira quando o servidor Flask não está disponível."""
    try:
        urllib.request.urlopen(f"{base_url}/login", timeout=3)
    except Exception:
        pytest.skip(f"Servidor Flask não disponível em {base_url} — skipping E2E suite")


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


@pytest.fixture(scope="session")
def creds_admin_global() -> dict:
    """Usado apenas pela captura de screenshots do onboarding (perfil admin_global)."""
    return {
        "email": os.environ.get("TEST_ADMIN_GLOBAL_EMAIL", ""),
        "password": os.environ.get("TEST_ADMIN_GLOBAL_PASSWORD", ""),
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


@pytest.fixture
def logged_in_admin_global(page: Page, base_url: str, creds_admin_global: dict):
    """Page já autenticada como admin_global (usado só na captura de screenshots)."""
    if not creds_admin_global["email"]:
        pytest.skip("TEST_ADMIN_GLOBAL_EMAIL não configurado")
    _do_login(page, base_url, creds_admin_global["email"], creds_admin_global["password"])
    return page
