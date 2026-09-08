"""OrangeHRM healing pipeline demos — intentionally broken locators for MCP repair."""

import pytest


@pytest.mark.pomhealer_demo
def test_orangehrm_broken_login_button(orangehrm_login, orangehrm_credentials):
    """Fails at login: wrong login button locator (Sign In vs Login)."""
    user, password = orangehrm_credentials
    orangehrm_login.goto()
    orangehrm_login.fill_username(user)
    orangehrm_login.fill_password(password)
    orangehrm_login.click_pomhealer_demo_login()


@pytest.mark.pomhealer_demo
def test_orangehrm_post_login_broken_heading(orangehrm_login, orangehrm_dashboard, orangehrm_credentials):
    """Logs in successfully, then fails on a broken dashboard heading locator."""
    user, password = orangehrm_credentials
    orangehrm_login.goto()
    orangehrm_login.login(user, password)
    orangehrm_dashboard.expect_pomhealer_demo_dashboard_visible()


@pytest.mark.pomhealer_demo
def test_orangehrm_broken_username_field(orangehrm_login, orangehrm_credentials):
    """Fails at login form: wrong username textbox locator (User Name vs Username)."""
    user, _password = orangehrm_credentials
    orangehrm_login.goto()
    orangehrm_login.fill_pomhealer_demo_username(user)


@pytest.mark.pomhealer_demo
def test_orangehrm_broken_pim_menu(orangehrm_login, orangehrm_dashboard, orangehrm_credentials):
    """Logs in successfully, then fails on a broken PIM sidepanel link locator."""
    user, password = orangehrm_credentials
    orangehrm_login.goto()
    orangehrm_login.login(user, password)
    orangehrm_dashboard.click_pomhealer_demo_pim()


@pytest.mark.pomhealer_demo
def test_orangehrm_broken_heading_with_storage_state(orangehrm_dashboard_authenticated):
    """Authenticated via storage_state fixture; fails on broken dashboard heading."""
    orangehrm_dashboard_authenticated.goto()
    orangehrm_dashboard_authenticated.expect_pomhealer_demo_dashboard_visible()
