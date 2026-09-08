"""Reference-app fixtures (page objects, demo browser settings, auth storage state)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page

from pages.orangehrm_dashboard_page import ORANGEHRM_DASHBOARD_URL, OrangeHrmDashboardPage
from pages.orangehrm_login_page import (
    ORANGEHRM_LOGIN_URL,
    ORANGEHRM_PASSWORD,
    ORANGEHRM_USERNAME,
    OrangeHrmLoginPage,
)
from pages.saucedemo_inventory_page import SAUCEDEMO_INVENTORY_URL, SauceDemoInventoryPage
from pages.saucedemo_login_page import (
    SAUCEDEMO_LOGIN_URL,
    SAUCEDEMO_PASSWORD,
    SAUCEDEMO_USERNAME,
    SauceDemoLoginPage,
)


def _demo_headless() -> bool:
    return os.environ.get("POMHEALER_DEMO_HEADLESS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_cred(user_key: str, password_key: str, default_user: str, default_password: str) -> tuple[str, str]:
    return (
        os.environ.get(user_key, default_user),
        os.environ.get(password_key, default_password),
    )


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("POMHEALER_BASE_URL", ORANGEHRM_LOGIN_URL)


@pytest.fixture(scope="session")
def orangehrm_credentials() -> tuple[str, str]:
    return _env_cred("ORANGEHRM_USER", "ORANGEHRM_PASSWORD", ORANGEHRM_USERNAME, ORANGEHRM_PASSWORD)


@pytest.fixture(scope="session")
def saucedemo_credentials() -> tuple[str, str]:
    return _env_cred("SAUCEDEMO_USER", "SAUCEDEMO_PASSWORD", SAUCEDEMO_USERNAME, SAUCEDEMO_PASSWORD)


@pytest.fixture(scope="session")
def browser_type_launch_args(pytestconfig, browser_type_launch_args):
    """Show the browser when running healing demos (unless POMHEALER_DEMO_HEADLESS=1)."""
    if not pytestconfig.getoption("--run-pomhealer-demo"):
        return browser_type_launch_args
    if _demo_headless():
        return {**browser_type_launch_args, "headless": True}
    slow_mo = int(os.environ.get("POMHEALER_DEMO_SLOW_MO", "400"))
    return {
        **browser_type_launch_args,
        "headless": False,
        "slow_mo": slow_mo,
    }


@pytest.fixture(scope="session")
def browser_context_args(pytestconfig, browser_context_args):
    if not pytestconfig.getoption("--run-pomhealer-demo"):
        return browser_context_args
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
    }


@pytest.fixture(autouse=True)
def _pomhealer_demo_timeouts(request):
    """Give public demo sites more time to load when running healing demos."""
    if not request.config.getoption("--run-pomhealer-demo"):
        yield
        return
    from pomhealer.timeouts import ACTION_TIMEOUT_MS, NAV_TIMEOUT_MS

    context = request.getfixturevalue("context")
    context.set_default_timeout(ACTION_TIMEOUT_MS)
    context.set_default_navigation_timeout(NAV_TIMEOUT_MS)
    yield


@pytest.fixture
def orangehrm_login(page: Page, base_url) -> OrangeHrmLoginPage:
    return OrangeHrmLoginPage(page, base_url)


@pytest.fixture
def orangehrm_dashboard(page: Page) -> OrangeHrmDashboardPage:
    return OrangeHrmDashboardPage(page, ORANGEHRM_DASHBOARD_URL)


@pytest.fixture
def saucedemo_login(page: Page) -> SauceDemoLoginPage:
    return SauceDemoLoginPage(page, SAUCEDEMO_LOGIN_URL)


@pytest.fixture
def saucedemo_inventory(page: Page) -> SauceDemoInventoryPage:
    return SauceDemoInventoryPage(page, SAUCEDEMO_INVENTORY_URL)


@pytest.fixture(scope="session")
def orangehrm_storage_state(browser, base_url, orangehrm_credentials) -> Path:
    """Login once; save storage state for authenticated healing / MCP restore."""
    from pomhealer.paths import AUTH_DIR, ensure_queue_dirs

    ensure_queue_dirs()
    path = AUTH_DIR.resolve_path() / "storage-state-orangehrm.json"
    context = browser.new_context()
    page = context.new_page()
    try:
        login = OrangeHrmLoginPage(page, base_url)
        login.goto()
        login.login(*orangehrm_credentials)
        context.storage_state(path=str(path))
    finally:
        context.close()
    return path


@pytest.fixture(scope="session")
def saucedemo_storage_state(browser, saucedemo_credentials) -> Path:
    from pomhealer.paths import AUTH_DIR, ensure_queue_dirs

    ensure_queue_dirs()
    path = AUTH_DIR.resolve_path() / "storage-state-saucedemo.json"
    context = browser.new_context()
    page = context.new_page()
    try:
        login = SauceDemoLoginPage(page, SAUCEDEMO_LOGIN_URL)
        login.goto()
        login.login(*saucedemo_credentials)
        context.storage_state(path=str(path))
    finally:
        context.close()
    return path


@pytest.fixture
def orangehrm_authenticated_page(browser, orangehrm_storage_state):
    context = browser.new_context(storage_state=str(orangehrm_storage_state))
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def saucedemo_authenticated_page(browser, saucedemo_storage_state):
    context = browser.new_context(storage_state=str(saucedemo_storage_state))
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def orangehrm_dashboard_authenticated(orangehrm_authenticated_page) -> OrangeHrmDashboardPage:
    return OrangeHrmDashboardPage(orangehrm_authenticated_page, ORANGEHRM_DASHBOARD_URL)


@pytest.fixture
def saucedemo_inventory_authenticated(saucedemo_authenticated_page) -> SauceDemoInventoryPage:
    return SauceDemoInventoryPage(saucedemo_authenticated_page, SAUCEDEMO_INVENTORY_URL)
