"""Ferramenta de captura de screenshots para o tour de onboarding.

NÃO é um teste de correção — não faz assertions, apenas navega logado como
cada usuário demo e salva recortes de tela em app/static/img/onboarding/.

Pré-requisitos:
    1. python scripts/seed_dados_demo_onboarding.py   (cria os usuários/chamados demo)
    2. flask run (ou equivalente) rodando localmente com credentials.json real
    3. .env.test preenchido com as credenciais dos usuários demo (ver .env.test.example)

Uso:
    pytest tests/e2e/test_capture_onboarding_screenshots.py -m capture --base-url http://127.0.0.1:5000
"""

import os

import pytest
from playwright.sync_api import Page

IMG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app",
    "static",
    "img",
    "onboarding",
)


def _salvar(page: Page, subpasta: str, nome_arquivo: str) -> None:
    pasta = os.path.join(IMG_DIR, subpasta)
    os.makedirs(pasta, exist_ok=True)
    page.wait_for_load_state("networkidle")
    page.screenshot(path=os.path.join(pasta, nome_arquivo))


@pytest.mark.capture
def test_capturar_screenshots_solicitante(logged_in_solicitante: Page, base_url: str) -> None:
    page = logged_in_solicitante

    page.goto(f"{base_url}/")
    _salvar(page, "solicitante", "02-novo-chamado.png")

    page.goto(f"{base_url}/meus-chamados")
    _salvar(page, "solicitante", "03-meus-chamados.png")

    linha = page.get_by_test_id("ticket-row").first
    if linha.count() > 0:
        linha.click()
        _salvar(page, "solicitante", "04-detalhe-chamado.png")
        _salvar(page, "solicitante", "05-editar-cancelar.png")
        _salvar(page, "solicitante", "06-confirmar-resolucao.png")

    page.goto(f"{base_url}/meus-chamados")
    _salvar(page, "solicitante", "08-notificacoes.png")


@pytest.mark.capture
def test_capturar_screenshots_supervisor(logged_in_supervisor: Page, base_url: str) -> None:
    page = logged_in_supervisor

    page.goto(f"{base_url}/painel")
    _salvar(page, "supervisor", "02-dashboard.png")
    _salvar(page, "supervisor", "04-filtros-sla.png")

    page.goto(f"{base_url}/admin/relatorios")
    _salvar(page, "supervisor", "05-relatorios.png")

    page.goto(f"{base_url}/exportar-avancado")
    _salvar(page, "supervisor", "06-exportar.png")


@pytest.mark.capture
def test_capturar_screenshots_admin(logged_in_admin: Page, base_url: str) -> None:
    page = logged_in_admin

    page.goto(f"{base_url}/admin")
    _salvar(page, "admin", "02-dashboard.png")

    page.goto(f"{base_url}/admin/relatorios")
    _salvar(page, "admin", "03-relatorios.png")

    page.goto(f"{base_url}/admin/usuarios")
    _salvar(page, "admin", "04-usuarios.png")

    page.goto(f"{base_url}/admin/categorias")
    _salvar(page, "admin", "05-categorias.png")

    page.goto(f"{base_url}/exportar-avancado")
    _salvar(page, "admin", "06-exportar.png")


@pytest.mark.capture
def test_capturar_screenshots_admin_global(logged_in_admin_global: Page, base_url: str) -> None:
    page = logged_in_admin_global

    page.goto(f"{base_url}/admin-global")
    _salvar(page, "admin_global", "dashboard.png")
