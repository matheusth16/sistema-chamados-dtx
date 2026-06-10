"""
Fluxo E2E — Logout.

Verifica que cada perfil consegue fazer logout e é redirecionado para /login.
Nenhum acesso a rota protegida deve ser possível após o logout.

Requer:
    pytest tests/e2e --base-url http://127.0.0.1:5000
    TEST_SOLICITANTE_EMAIL=...  TEST_SUPERVISOR_EMAIL=...  TEST_ADMIN_EMAIL=...
"""

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import DEFAULT_TIMEOUT


def _assert_logged_out(page: Page, base_url: str) -> None:
    """Verifica que o usuário está deslogado: redirecionado ao tentar acessar rota protegida."""
    page.goto(f"{base_url}/meus-chamados")
    page.wait_for_load_state("networkidle")
    assert "/login" in page.url, (
        f"Esperado redirecionar para /login após logout, mas URL é: {page.url}"
    )


@pytest.mark.e2e
def test_logout_solicitante(logged_in_solicitante: Page, base_url: str) -> None:
    """LOGOUT-01: Solicitante faz logout e é redirecionado para /login."""
    page = logged_in_solicitante
    page.goto(f"{base_url}/logout")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
    assert "/login" in page.url, f"Logout deveria redirecionar para /login. URL: {page.url}"


@pytest.mark.e2e
def test_logout_solicitante_invalida_sessao(logged_in_solicitante: Page, base_url: str) -> None:
    """LOGOUT-02: Após logout, solicitante não consegue acessar rota protegida."""
    page = logged_in_solicitante
    page.goto(f"{base_url}/logout")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
    _assert_logged_out(page, base_url)


@pytest.mark.e2e
def test_logout_supervisor(logged_in_supervisor: Page, base_url: str) -> None:
    """LOGOUT-03: Supervisor faz logout e é redirecionado para /login."""
    page = logged_in_supervisor
    page.goto(f"{base_url}/logout")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
    assert "/login" in page.url, f"Logout deveria redirecionar para /login. URL: {page.url}"


@pytest.mark.e2e
def test_logout_admin(logged_in_admin: Page, base_url: str) -> None:
    """LOGOUT-04: Admin faz logout e é redirecionado para /login."""
    page = logged_in_admin
    page.goto(f"{base_url}/logout")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
    assert "/login" in page.url, f"Logout deveria redirecionar para /login. URL: {page.url}"


@pytest.mark.e2e
def test_logout_admin_invalida_sessao(logged_in_admin: Page, base_url: str) -> None:
    """LOGOUT-05: Após logout, admin não acessa rotas administrativas."""
    page = logged_in_admin
    page.goto(f"{base_url}/logout")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
    assert "/login" in page.url, (
        f"Sessão de admin deveria ser invalidada após logout. URL: {page.url}"
    )
