"""Page Object Model para a página 'Meus Chamados'."""

from playwright.sync_api import Page, expect


class MeusChamadosPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

        # Locators
        self.total_chamados = page.get_by_test_id("total-chamados")
        self.new_ticket_btn = page.get_by_test_id("new-ticket-btn")
        self.ticket_rows = page.get_by_test_id("ticket-row")

    def navigate(self) -> None:
        self.page.goto(f"{self.base_url}/meus_chamados")
        self.page.wait_for_load_state("networkidle")

    def assert_page_visible(self) -> None:
        expect(self.new_ticket_btn).to_be_visible()

    def get_ticket_count(self) -> int:
        return self.ticket_rows.count()

    def assert_has_tickets(self) -> None:
        expect(self.ticket_rows.first).to_be_visible()

    def assert_ticket_with_description(self, descricao_prefix: str) -> None:
        """Verifica que alguma linha contém o texto da descrição."""
        row = self.page.locator(f'[data-testid="ticket-row"]:has-text("{descricao_prefix}")')
        expect(row).to_be_visible()
