"""Auditorias axe-core nas páginas públicas e autenticadas principais."""

from pathlib import Path

import pytest
from playwright.sync_api import Page

AXE_PATH = Path(__file__).resolve().parents[2] / "node_modules" / "axe-core" / "axe.min.js"
BLOCKING_IMPACTS = {"critical", "serious"}


def _assert_no_blocking_axe_violations(page: Page, page_name: str) -> None:
    if not AXE_PATH.is_file():
        pytest.fail("axe-core não instalado. Execute `npm ci` antes da suíte a11y.")

    # Executar o bundle no contexto da página evita bloqueio pela CSP com nonce
    # da aplicação; nenhuma regra axe é desativada.
    page.evaluate(AXE_PATH.read_text(encoding="utf-8"))
    results = page.evaluate(
        """async () => await axe.run(document, {
            resultTypes: ["violations"]
        })"""
    )
    blocking = [
        violation
        for violation in results["violations"]
        if violation.get("impact") in BLOCKING_IMPACTS
    ]
    if not blocking:
        return

    details = []
    for violation in blocking:
        targets = [", ".join(node["target"]) for node in violation["nodes"][:5]]
        details.append(
            f"- {violation['id']} ({violation['impact']}): {violation['help']} "
            f"[alvos: {'; '.join(targets)}]"
        )
    pytest.fail(
        f"{page_name} contém {len(blocking)} violação(ões) axe serious/critical:\n"
        + "\n".join(details)
    )


@pytest.mark.a11y
@pytest.mark.e2e
def test_login_publico_sem_violacoes_bloqueantes(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/login")
    page.wait_for_load_state("networkidle")

    _assert_no_blocking_axe_violations(page, "Login público")


@pytest.mark.a11y
@pytest.mark.e2e
def test_solicitante_sem_violacoes_bloqueantes(logged_in_solicitante: Page, base_url: str) -> None:
    page = logged_in_solicitante
    page.goto(f"{base_url}/meus-chamados")
    page.wait_for_load_state("networkidle")

    _assert_no_blocking_axe_violations(page, "Meus chamados do solicitante")


@pytest.mark.a11y
@pytest.mark.e2e
def test_supervisor_sem_violacoes_bloqueantes(logged_in_supervisor: Page, base_url: str) -> None:
    page = logged_in_supervisor
    page.goto(f"{base_url}/admin")
    page.wait_for_load_state("networkidle")

    _assert_no_blocking_axe_violations(page, "Dashboard do supervisor")


@pytest.mark.a11y
@pytest.mark.e2e
def test_admin_sem_violacoes_bloqueantes(logged_in_admin: Page, base_url: str) -> None:
    page = logged_in_admin
    page.goto(f"{base_url}/admin/usuarios")
    page.wait_for_load_state("networkidle")

    _assert_no_blocking_axe_violations(page, "Gerenciamento de usuários do admin")
