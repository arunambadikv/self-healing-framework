"""Sauce Demo healing pipeline demos — intentionally broken locators for MCP repair."""

import pytest

from pages.saucedemo_login_page import SAUCEDEMO_PASSWORD, SAUCEDEMO_USERNAME


@pytest.mark.healing_demo
def test_saucedemo_broken_login_button(saucedemo_login, saucedemo_credentials):
    """Fails at login: wrong login button locator (Sign In vs Login)."""
    user, password = saucedemo_credentials
    saucedemo_login.goto()
    saucedemo_login.fill_username(user)
    saucedemo_login.fill_password(password)
    saucedemo_login.click_healing_demo_login()


@pytest.mark.healing_demo
def test_saucedemo_broken_inventory_add_to_cart(saucedemo_login, saucedemo_inventory, saucedemo_credentials):
    """Logs in, then fails on a broken inventory Add to cart locator (multi-page auth)."""
    user, password = saucedemo_credentials
    saucedemo_login.goto()
    saucedemo_login.login(user, password)
    saucedemo_inventory.goto()
    saucedemo_inventory.click_healing_demo_add_backpack()


@pytest.mark.healing_demo
def test_saucedemo_broken_inventory_with_storage_state(saucedemo_inventory_authenticated):
    """Authenticated via storage_state fixture; fails on broken Add to cart locator."""
    saucedemo_inventory_authenticated.goto()
    saucedemo_inventory_authenticated.click_healing_demo_add_backpack()
