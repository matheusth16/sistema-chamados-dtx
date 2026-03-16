"""
Fluxo E2E — Admin.

Fluxo principal:
  1. Login como admin
  2. Acessa gerenciamento de usuários
  3. Verifica acesso a categorias e traduções

Requer:
    pytest tests/e2e --base-url http://127.0.0.1:5000
    TEST_ADMIN_EMAIL=...  TEST_ADMIN_PASSWORD=...
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_admin_acessa_dashboard(
    logged_in_admin: Page, base_url: str
) -> None:
    """Admin deve aterrissar fora do /login após autenticação."""
    page = logged_in_admin
    assert "/login" not in page.url


@pytest.mark.e2e
def test_admin_acessa_gerenciamento_usuarios(
    logged_in_admin: Page, base_url: str
) -> None:
    """Admin deve acessar /admin/usuarios sem redirecionamento."""
    page = logged_in_admin
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")

    assert "/login" not in page.url
    assert "/admin/usuarios" in page.url


@pytest.mark.e2e
def test_admin_acessa_categorias(
    logged_in_admin: Page, base_url: str
) -> None:
    """Admin deve acessar gerenciamento de categorias."""
    page = logged_in_admin
    page.goto(f"{base_url}/admin/categorias")
    page.wait_for_load_state("networkidle")

    assert "/login" not in page.url


@pytest.mark.e2e
def test_admin_acessa_traducoes(
    logged_in_admin: Page, base_url: str
) -> None:
    """Admin deve acessar o painel de traduções."""
    page = logged_in_admin
    page.goto(f"{base_url}/admin/traducoes")
    page.wait_for_load_state("networkidle")

    assert "/login" not in page.url


@pytest.mark.e2e
def test_admin_acessa_relatorios(
    logged_in_admin: Page, base_url: str
) -> None:
    """Admin deve acessar relatórios."""
    page = logged_in_admin
    page.goto(f"{base_url}/relatorios")
    page.wait_for_load_state("networkidle")

    assert "/login" not in page.url
