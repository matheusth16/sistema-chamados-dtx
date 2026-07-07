"""
Fluxo E2E — Admin Global.

Fluxo principal:
  1. Login como admin_global
  2. Acessa painel exclusivo /admin-global
  3. Acessa gerenciamento de usuários/categorias (herdado de admin)

Antes só existia a fixture `logged_in_admin_global`, usada apenas na captura de
screenshots de onboarding — não havia teste funcional de acesso para o perfil.
Os fluxos de mutação (promover/rebaixar, bloqueio de edição do admin raiz) já
são cobertos a nível de rota em test_admin_global.py e test_usuarios.py; este
arquivo foca em verificação via browser real, no mesmo padrão dos irmãos
test_fluxo_admin.py / test_fluxo_supervisor.py (sem mutar dados do ambiente).

Requer:
    pytest tests/e2e --base-url http://127.0.0.1:5000
    TEST_ADMIN_GLOBAL_EMAIL=...  TEST_ADMIN_GLOBAL_PASSWORD=...
"""

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import DEFAULT_TIMEOUT
from tests.e2e.pages.dashboard_page import DashboardPage


@pytest.mark.e2e
def test_admin_global_acessa_dashboard(logged_in_admin_global: Page, base_url: str) -> None:
    """Admin_global deve aterrissar fora do /login após autenticação."""
    page = logged_in_admin_global
    assert "/login" not in page.url


@pytest.mark.e2e
def test_admin_global_acessa_painel_exclusivo(logged_in_admin_global: Page, base_url: str) -> None:
    """Admin_global deve acessar /admin-global (rota exclusiva do perfil) sem redirecionamento."""
    page = logged_in_admin_global
    page.goto(f"{base_url}/admin-global")
    page.wait_for_load_state("networkidle")

    assert "/login" not in page.url
    assert "/admin-global" in page.url


@pytest.mark.e2e
def test_admin_global_acessa_gerenciamento_usuarios(
    logged_in_admin_global: Page, base_url: str
) -> None:
    """Admin_global herda acesso a /admin/usuarios (permissão de admin)."""
    page = logged_in_admin_global
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")

    assert "/login" not in page.url
    assert "/admin/usuarios" in page.url


@pytest.mark.e2e
def test_admin_global_acessa_categorias(logged_in_admin_global: Page, base_url: str) -> None:
    """Admin_global herda acesso a /admin/categorias (permissão de admin)."""
    page = logged_in_admin_global
    page.goto(f"{base_url}/admin/categorias")
    page.wait_for_load_state("networkidle")

    assert "/login" not in page.url


@pytest.mark.e2e
def test_admin_global_dashboard_container_visivel(
    logged_in_admin_global: Page, base_url: str
) -> None:
    """Admin_global acessa /admin e vê o container principal do dashboard (data-testid)."""
    page = logged_in_admin_global
    dashboard = DashboardPage(page, base_url)
    dashboard.navigate()
    dashboard.assert_dashboard_visible()


@pytest.mark.e2e
def test_admin_global_painel_exclusivo_tem_conteudo(
    logged_in_admin_global: Page, base_url: str
) -> None:
    """Admin_global acessa /admin-global e vê a página com conteúdo renderizado."""
    page = logged_in_admin_global
    page.goto(f"{base_url}/admin-global")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    assert "/login" not in page.url
    body_text = page.locator("body").inner_text()
    assert len(body_text.strip()) > 0, "Página /admin-global não deve estar em branco"
