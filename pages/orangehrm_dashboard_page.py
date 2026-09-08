"""OrangeHRM dashboard page — post-login locators."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage

ORANGEHRM_DASHBOARD_URL = (
    "https://opensource-demo.orangehrmlive.com/web/index.php/dashboard/index"
)


class OrangeHrmDashboardPage(BasePage):
    @property
    def dashboard_heading(self) -> Locator:
        return self.page.get_by_role("heading", name="Dashboard")

    @property
    def pomhealer_demo_dashboard_heading(self) -> Locator:
        """Healing demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("heading", name="Home")

    @property
    def pomhealer_demo_pim_link(self) -> Locator:
        """Healing demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("link", name="Employee List")

    def ready_locator(self) -> Locator:
        return self.dashboard_heading

    def expect_dashboard_visible(self) -> None:
        self._expect_visible(
            "expect_dashboard_visible",
            "dashboard_heading",
            self.dashboard_heading,
        )

    def expect_pomhealer_demo_dashboard_visible(self) -> None:
        self._expect_visible(
            "expect_pomhealer_demo_dashboard_visible",
            "pomhealer_demo_dashboard_heading",
            self.pomhealer_demo_dashboard_heading,
        )

    def click_pomhealer_demo_pim(self) -> None:
        self._click_locator(
            "click_pomhealer_demo_pim",
            "pomhealer_demo_pim_link",
            self.pomhealer_demo_pim_link,
        )
