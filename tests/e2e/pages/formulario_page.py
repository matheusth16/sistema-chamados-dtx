"""Page Object Model para o formulário de abertura de chamado."""

from playwright.sync_api import Page, expect


class FormularioPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

        # Locators
        self.form = page.get_by_test_id("chamado-form")
        self.tipo_select = page.get_by_test_id("tipo-select")
        self.descricao_textarea = page.get_by_test_id("descricao-textarea")
        self.submit_btn = page.get_by_test_id("submit-btn")

    def navigate(self) -> None:
        self.page.goto(f"{self.base_url}/")
        self.page.wait_for_load_state("networkidle")

    def fill_and_submit(self, tipo: str, descricao: str) -> None:
        self.navigate()
        self.tipo_select.select_option(label=tipo)
        self.descricao_textarea.fill(descricao)
        self.submit_btn.click()
        self.page.wait_for_load_state("networkidle")

    def assert_form_visible(self) -> None:
        expect(self.form).to_be_visible()
        expect(self.tipo_select).to_be_visible()
        expect(self.descricao_textarea).to_be_visible()
        expect(self.submit_btn).to_be_visible()
