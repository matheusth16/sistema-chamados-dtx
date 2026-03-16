"""Page Object Model para a página de login."""

from playwright.sync_api import Page, expect


class LoginPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

        # Locators
        self.email_input = page.get_by_test_id("email-input")
        self.password_input = page.get_by_test_id("password-input")
        self.submit_btn = page.get_by_test_id("login-submit-btn")
        self.flash_message = page.get_by_test_id("flash-message")

    def navigate(self) -> None:
        self.page.goto(f"{self.base_url}/login")
        self.page.wait_for_load_state("networkidle")

    def login(self, email: str, password: str) -> None:
        self.navigate()
        self.email_input.fill(email)
        self.password_input.fill(password)
        self.submit_btn.click()
        self.page.wait_for_load_state("networkidle")

    def assert_login_page_visible(self) -> None:
        expect(self.email_input).to_be_visible()
        expect(self.password_input).to_be_visible()
        expect(self.submit_btn).to_be_visible()

    def assert_error_message_visible(self) -> None:
        expect(self.flash_message).to_be_visible()

    def assert_logged_in(self) -> None:
        """Verifica que o login foi bem-sucedido (URL mudou para fora de /login)."""
        expect(self.page).not_to_have_url(f"{self.base_url}/login")
