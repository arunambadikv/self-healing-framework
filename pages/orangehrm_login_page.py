"""OrangeHRM login page — locators live here (Python-only POM)."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage

ORANGEHRM_LOGIN_URL = (
    "https://opensource-demo.orangehrmlive.com/web/index.php/auth/login"
)
ORANGEHRM_USERNAME = "Admin"
ORANGEHRM_PASSWORD = "admin123"


class OrangeHrmLoginPage(BasePage):
    @property
    def username_input(self) -> Locator:
        return self.page.get_by_role("textbox", name="Username")

    @property
    def password_input(self) -> Locator:
        return self.page.get_by_role("textbox", name="Password")

    @property
    def login_button(self) -> Locator:
        return self.page.get_by_role("button", name="Login")

    @property
    def healing_demo_login_button(self) -> Locator:
        """Healing demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("button", name="Sign In")

    @property
    def healing_demo_username_input(self) -> Locator:
        """Healing demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("textbox", name="User Name")

    def fill_username(self, value: str) -> None:
        self._fill_locator("fill_username", "username_input", self.username_input, value)

    def fill_password(self, value: str) -> None:
        self._fill_locator("fill_password", "password_input", self.password_input, value)

    def fill_healing_demo_username(self, value: str) -> None:
        self._fill_locator(
            "fill_healing_demo_username",
            "healing_demo_username_input",
            self.healing_demo_username_input,
            value,
        )

    def click_login(self) -> None:
        self._click_locator("click_login", "login_button", self.login_button)

    def click_healing_demo_login(self) -> None:
        self._click_locator(
            "click_healing_demo_login",
            "healing_demo_login_button",
            self.healing_demo_login_button,
        )

    def login(self, username: str, password: str) -> None:
        self.fill_username(username)
        self.fill_password(password)
        self.click_login()
