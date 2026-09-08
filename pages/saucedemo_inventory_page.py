"""Sauce Demo inventory (post-login) — locators for multi-page healing demos."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage

SAUCEDEMO_INVENTORY_URL = "https://www.saucedemo.com/inventory.html"


class SauceDemoInventoryPage(BasePage):
    @property
    def inventory_list(self) -> Locator:
        return self.page.locator(".inventory_list")

    @property
    def add_backpack_button(self) -> Locator:
        return self.page.get_by_role("button", name="Add to cart").first

    @property
    def pomhealer_demo_add_backpack(self) -> Locator:
        """Healing demo: intentionally broken until MCP repair."""
        return self.page.get_by_role("button", name="Add Backpack")

    @property
    def shopping_cart_link(self) -> Locator:
        return self.page.locator(".shopping_cart_link")

    def ready_locator(self) -> Locator:
        return self.inventory_list

    def click_add_backpack(self) -> None:
        self._click_locator("click_add_backpack", "add_backpack_button", self.add_backpack_button)

    def click_pomhealer_demo_add_backpack(self) -> None:
        self._click_locator(
            "click_pomhealer_demo_add_backpack",
            "pomhealer_demo_add_backpack",
            self.pomhealer_demo_add_backpack,
        )

    def open_cart(self) -> None:
        self._click_locator("open_cart", "shopping_cart_link", self.shopping_cart_link)
