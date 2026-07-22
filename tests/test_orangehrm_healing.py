"""OrangeHRM healing pipeline demos — intentionally broken locators for MCP repair."""

import pytest

from pages.orangehrm_login_page import ORANGEHRM_PASSWORD, ORANGEHRM_USERNAME


@pytest.mark.healing_demo
def test_orangehrm_broken_login_button(orangehrm_login):
    """Fails at login: wrong login button locator (Sign In vs Login)."""
    orangehrm_login.goto()
    orangehrm_login.fill_username(ORANGEHRM_USERNAME)
    orangehrm_login.fill_password(ORANGEHRM_PASSWORD)
    orangehrm_login.click_healing_demo_login()


@pytest.mark.healing_demo
def test_orangehrm_post_login_broken_heading(orangehrm_login, orangehrm_dashboard):
    """Logs in successfully, then fails on a broken dashboard heading locator."""
    orangehrm_login.goto()
    orangehrm_login.login(ORANGEHRM_USERNAME, ORANGEHRM_PASSWORD)
    orangehrm_dashboard.expect_healing_demo_dashboard_visible()


@pytest.mark.healing_demo
def test_orangehrm_broken_username_field(orangehrm_login):
    """Fails at login form: wrong username textbox locator (User Name vs Username)."""
    orangehrm_login.goto()
    orangehrm_login.fill_healing_demo_username(ORANGEHRM_USERNAME)


@pytest.mark.healing_demo
def test_orangehrm_broken_pim_menu(orangehrm_login, orangehrm_dashboard):
    """Logs in successfully, then fails on a broken PIM sidepanel link locator."""
    orangehrm_login.goto()
    orangehrm_login.login(ORANGEHRM_USERNAME, ORANGEHRM_PASSWORD)
    orangehrm_dashboard.click_healing_demo_pim()
