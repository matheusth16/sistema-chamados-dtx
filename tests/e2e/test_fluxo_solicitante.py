"""
Fluxo E2E — Solicitante.

Fluxo principal:
  1. Login como solicitante
  2. Acessa formulário de abertura de chamado
  3. Preenche e envia
  4. Verifica que o chamado aparece em "Meus Chamados"

Requer:
    pytest tests/e2e --base-url http://127.0.0.1:5000
    TEST_SOLICITANTE_EMAIL=...  TEST_SOLICITANTE_PASSWORD=...
"""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.pages.formulario_page import FormularioPage
from tests.e2e.pages.login_page import LoginPage
from tests.e2e.pages.meus_chamados_page import MeusChamadosPage


@pytest.mark.e2e
def test_login_page_carrega(page: Page, base_url: str) -> None:
    """Smoke: a página de login carrega com título correto."""
    login = LoginPage(page, base_url)
    login.navigate()
    expect(page).to_have_title(re.compile(r"Login", re.IGNORECASE))
    login.assert_login_page_visible()


@pytest.mark.e2e
def test_login_invalido_exibe_erro(page: Page, base_url: str) -> None:
    """Login com credenciais inválidas deve exibir mensagem de erro."""
    login = LoginPage(page, base_url)
    login.login(email="naoexiste@dtx.com", password="senhaerrada")
    login.assert_error_message_visible()


@pytest.mark.e2e
def test_fluxo_completo_solicitante(
    logged_in_solicitante: Page, base_url: str
) -> None:
    """
    Fluxo: login → abrir chamado → verificar em Meus Chamados.

    Skipped automaticamente se TEST_SOLICITANTE_EMAIL não estiver configurado.
    """
    page = logged_in_solicitante
    descricao_teste = "Chamado E2E automatizado - pode ignorar"

    # 1. Abre formulário e preenche
    formulario = FormularioPage(page, base_url)
    formulario.navigate()
    formulario.assert_form_visible()
    formulario.descricao_textarea.fill(descricao_teste)
    formulario.submit_btn.click()
    page.wait_for_load_state("networkidle")

    # 2. Navega para Meus Chamados e verifica que o chamado aparece
    meus_chamados = MeusChamadosPage(page, base_url)
    meus_chamados.navigate()
    meus_chamados.assert_page_visible()
    meus_chamados.assert_has_tickets()


@pytest.mark.e2e
def test_solicitante_nao_acessa_admin(
    logged_in_solicitante: Page, base_url: str
) -> None:
    """Solicitante não deve conseguir acessar rotas de admin."""
    page = logged_in_solicitante
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")

    # Deve ser redirecionado (não permanecer em /admin/usuarios)
    assert "/admin/usuarios" not in page.url or page.url.endswith("/login")
