"""
Suíte E2E smoke — fluxos críticos obrigatórios.

Padrões anti-flake aplicados:
- Seletores data-testid estáveis (nunca CSS frágil)
- wait_for_load_state("networkidle") após navegação
- Timeouts explícitos em todas as assertions (DEFAULT_TIMEOUT)
- Isolamento por cenário (page fixture function-scoped — padrão do Playwright)
- Auto-skip via require_server quando servidor não disponível

Uso:
    pytest tests/e2e -m smoke --base-url http://127.0.0.1:5000
    FLASK_TEST_URL=https://staging.example.com pytest tests/e2e -m smoke
"""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import DEFAULT_TIMEOUT
from tests.e2e.pages.dashboard_page import DashboardPage
from tests.e2e.pages.formulario_page import FormularioPage
from tests.e2e.pages.login_page import LoginPage
from tests.e2e.pages.meus_chamados_page import MeusChamadosPage

# ── SMOKE-01: Acesso público ──────────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_login_page_carrega(page: Page, base_url: str) -> None:
    """SMOKE-01: Página de login carrega e exibe elementos essenciais."""
    login = LoginPage(page, base_url)
    login.navigate()
    login.assert_login_page_visible()
    expect(page).to_have_title(re.compile(r"login", re.IGNORECASE), timeout=DEFAULT_TIMEOUT)


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_login_invalido_exibe_erro(page: Page, base_url: str) -> None:
    """SMOKE-02: Credenciais inválidas exibem mensagem de erro sem redirecionar."""
    login = LoginPage(page, base_url)
    login.login(email="invalido@teste.com", password="senhaerrada")
    # Deve permanecer em /login ou mostrar mensagem de erro
    login.assert_error_message_visible()


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_rota_protegida_redireciona_para_login(page: Page, base_url: str) -> None:
    """SMOKE-03: Acesso sem autenticação a rota protegida redireciona para login."""
    page.goto(f"{base_url}/admin")
    page.wait_for_load_state("networkidle")
    assert "/login" in page.url, f"Esperado redirect para /login, mas URL é: {page.url}"


# ── SMOKE-04 a 06: Login por perfil ──────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_login_solicitante(logged_in_solicitante: Page, base_url: str) -> None:
    """SMOKE-04: Solicitante faz login e aterra fora de /login."""
    page = logged_in_solicitante
    assert "/login" not in page.url, f"Login falhou, URL ainda: {page.url}"


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_login_supervisor(logged_in_supervisor: Page, base_url: str) -> None:
    """SMOKE-05: Supervisor faz login e aterra no dashboard."""
    page = logged_in_supervisor
    assert "/login" not in page.url, f"Login falhou, URL ainda: {page.url}"


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_login_admin(logged_in_admin: Page, base_url: str) -> None:
    """SMOKE-06: Admin faz login e aterra no dashboard."""
    page = logged_in_admin
    assert "/login" not in page.url, f"Login falhou, URL ainda: {page.url}"


# ── SMOKE-07 a 08: Controle de acesso ────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_solicitante_nao_acessa_admin_usuarios(
    logged_in_solicitante: Page, base_url: str
) -> None:
    """SMOKE-07: Solicitante bloqueado em /admin/usuarios — redireciona."""
    page = logged_in_solicitante
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")
    assert "/admin/usuarios" not in page.url, (
        f"Solicitante não deveria acessar /admin/usuarios. URL: {page.url}"
    )


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_supervisor_nao_acessa_admin_usuarios(
    logged_in_supervisor: Page, base_url: str
) -> None:
    """SMOKE-08: Supervisor bloqueado em /admin/usuarios — redireciona."""
    page = logged_in_supervisor
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")
    assert "/admin/usuarios" not in page.url, (
        f"Supervisor não deveria acessar /admin/usuarios. URL: {page.url}"
    )


# ── SMOKE-09: Abertura de chamado ─────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_abertura_chamado_formulario_visivel(
    logged_in_solicitante: Page, base_url: str
) -> None:
    """SMOKE-09: Solicitante acessa formulário de abertura de chamado."""
    page = logged_in_solicitante
    formulario = FormularioPage(page, base_url)
    formulario.navigate()
    formulario.assert_form_visible()


# ── SMOKE-10: Dashboard supervisor/admin ────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_supervisor_acessa_dashboard(logged_in_supervisor: Page, base_url: str) -> None:
    """SMOKE-10: Supervisor acessa dashboard e vê container principal."""
    page = logged_in_supervisor
    dashboard = DashboardPage(page, base_url)
    dashboard.navigate()
    dashboard.assert_dashboard_visible()


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_admin_acessa_dashboard(logged_in_admin: Page, base_url: str) -> None:
    """SMOKE-11: Admin acessa dashboard e vê container principal."""
    page = logged_in_admin
    dashboard = DashboardPage(page, base_url)
    dashboard.navigate()
    dashboard.assert_dashboard_visible()


# ── SMOKE-12: Meus Chamados ───────────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_solicitante_meus_chamados_carrega(
    logged_in_solicitante: Page, base_url: str
) -> None:
    """SMOKE-12: Solicitante acessa /meus-chamados sem erro."""
    page = logged_in_solicitante
    meus_chamados = MeusChamadosPage(page, base_url)
    meus_chamados.navigate()
    meus_chamados.assert_page_visible()


# ── SMOKE-13: Rotas admin exclusivas ─────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_admin_acessa_gerenciamento_usuarios(logged_in_admin: Page, base_url: str) -> None:
    """SMOKE-13: Admin acessa /admin/usuarios sem ser bloqueado."""
    page = logged_in_admin
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")
    assert "/login" not in page.url, f"Admin deveria acessar /admin/usuarios. URL: {page.url}"
    assert "/admin/usuarios" in page.url


@pytest.mark.smoke
@pytest.mark.e2e
def test_smoke_admin_acessa_relatorios(logged_in_admin: Page, base_url: str) -> None:
    """SMOKE-14: Admin acessa /admin/relatorios sem erro."""
    page = logged_in_admin
    page.goto(f"{base_url}/admin/relatorios")
    page.wait_for_load_state("networkidle")
    assert "/login" not in page.url, f"Admin deveria ver relatórios. URL: {page.url}"
