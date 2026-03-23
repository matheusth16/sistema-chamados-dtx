"""Page Object Model para o dashboard de admin/supervisor."""

from playwright.sync_api import Page, expect

DEFAULT_TIMEOUT = 10_000  # ms


class DashboardPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url
        self.container = page.get_by_test_id("dashboard-container")
        self.chamado_rows = page.get_by_test_id("chamado-row")

    def navigate(self) -> None:
        self.page.goto(f"{self.base_url}/admin")
        self.page.wait_for_load_state("networkidle")

    def assert_dashboard_visible(self) -> None:
        expect(self.container).to_be_visible(timeout=DEFAULT_TIMEOUT)

    def get_ticket_count(self) -> int:
        return self.chamado_rows.count()
