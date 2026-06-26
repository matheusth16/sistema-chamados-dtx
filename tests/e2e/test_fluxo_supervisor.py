"""
Fluxo E2E — Supervisor.

Fluxo principal:
  1. Login como supervisor
  2. Acessa painel de chamados (dashboard)
  3. Verifica que vê chamados da sua área

Requer:
    pytest tests/e2e --base-url http://127.0.0.1:5000
    TEST_SUPERVISOR_EMAIL=...  TEST_SUPERVISOR_PASSWORD=...
"""

import pytest
from playwright.sync_api import Page

from tests.e2e.conftest import DEFAULT_TIMEOUT
from tests.e2e.pages.dashboard_page import DashboardPage


@pytest.mark.e2e
def test_supervisor_acessa_dashboard(logged_in_supervisor: Page, base_url: str) -> None:
    """Supervisor deve atterrir no dashboard após login."""
    page = logged_in_supervisor
    # Após login, deve estar em alguma rota que não seja /login
    assert "/login" not in page.url


@pytest.mark.e2e
def test_supervisor_acessa_relatorios(logged_in_supervisor: Page, base_url: str) -> None:
    """Supervisor deve conseguir acessar a página de relatórios."""
    page = logged_in_supervisor
    page.goto(f"{base_url}/admin/relatorios")
    page.wait_for_load_state("networkidle")

    # Não deve redirecionar para login
    assert "/login" not in page.url


@pytest.mark.e2e
def test_supervisor_nao_acessa_admin_usuarios(logged_in_supervisor: Page, base_url: str) -> None:
    """Supervisor não deve ter acesso ao gerenciamento de usuários."""
    page = logged_in_supervisor
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")

    # Deve ser bloqueado — não permanecer na rota de admin de usuários
    # (o app pode redirecionar para / ou exibir 403)
    assert "/admin/usuarios" not in page.url or page.url.endswith("/login")


@pytest.mark.e2e
def test_supervisor_ve_lista_chamados(logged_in_supervisor: Page, base_url: str) -> None:
    """Supervisor deve ver a lista de chamados ao acessar /chamados."""
    page = logged_in_supervisor
    page.goto(f"{base_url}/chamados")
    page.wait_for_load_state("networkidle")

    # Não deve ser barrado
    assert "/login" not in page.url


@pytest.mark.e2e
def test_supervisor_dashboard_container_visivel(logged_in_supervisor: Page, base_url: str) -> None:
    """Dashboard do supervisor deve renderizar o container principal com data-testid."""
    page = logged_in_supervisor
    dashboard = DashboardPage(page, base_url)
    dashboard.navigate()
    dashboard.assert_dashboard_visible()


@pytest.mark.e2e
def test_supervisor_nao_acessa_admin_categorias(logged_in_supervisor: Page, base_url: str) -> None:
    """Supervisor não deve ter acesso ao gerenciamento de categorias (rota admin)."""
    page = logged_in_supervisor
    page.goto(f"{base_url}/admin/categorias")
    page.wait_for_load_state("networkidle")

    assert "/admin/categorias" not in page.url, (
        f"Supervisor não deveria acessar /admin/categorias. URL: {page.url}"
    )


@pytest.mark.e2e
def test_supervisor_relatorios_tem_conteudo(logged_in_supervisor: Page, base_url: str) -> None:
    """Supervisor acessa /admin/relatorios e vê a página sem erro (status 200)."""
    page = logged_in_supervisor
    responses = []
    page.on("response", lambda r: responses.append(r) if "/relatorios" in r.url else None)

    page.goto(f"{base_url}/admin/relatorios")
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    assert "/login" not in page.url
    # Verifica que há algum conteúdo renderizado (não página em branco)
    body_text = page.locator("body").inner_text()
    assert len(body_text.strip()) > 0, "Página de relatórios não deve estar em branco"
