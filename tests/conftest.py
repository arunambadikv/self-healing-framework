import os
from pathlib import Path

import pytest
from playwright.sync_api import Page

from pages.orangehrm_dashboard_page import ORANGEHRM_DASHBOARD_URL, OrangeHrmDashboardPage
from pages.orangehrm_login_page import ORANGEHRM_LOGIN_URL, OrangeHrmLoginPage
from healing.step_trace import StepTraceCollector, reset_step_trace, set_active_step_trace


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("HEALING_BASE_URL", ORANGEHRM_LOGIN_URL)


@pytest.fixture(scope="session")
def browser_type_launch_args(pytestconfig, browser_type_launch_args):
    """Show the browser when running healing demos."""
    if not pytestconfig.getoption("--run-healing-demo"):
        return browser_type_launch_args
    slow_mo = int(os.environ.get("HEALING_DEMO_SLOW_MO", "400"))
    return {
        **browser_type_launch_args,
        "headless": False,
        "slow_mo": slow_mo,
    }


@pytest.fixture(scope="session")
def browser_context_args(pytestconfig, browser_context_args):
    if not pytestconfig.getoption("--run-healing-demo"):
        return browser_context_args
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
    }


@pytest.fixture
def orangehrm_login(page: Page, base_url) -> OrangeHrmLoginPage:
    return OrangeHrmLoginPage(page, base_url)


@pytest.fixture
def orangehrm_dashboard(page: Page) -> OrangeHrmDashboardPage:
    return OrangeHrmDashboardPage(page, ORANGEHRM_DASHBOARD_URL)


@pytest.fixture(autouse=True)
def _healing_step_trace(request):
    module_stem = Path(str(request.node.fspath)).stem
    collector = StepTraceCollector(
        test_name=request.node.name,
        test_module=module_stem,
    )
    token = set_active_step_trace(collector)
    request.node._healing_step_trace = collector  # type: ignore[attr-defined]
    yield
    reset_step_trace(token)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or report.passed:
        return

    exc = call.excinfo.value if call.excinfo else None
    if exc is None:
        return

    collector = getattr(item, "_healing_step_trace", None)
    base_url = os.environ.get("HEALING_BASE_URL", ORANGEHRM_LOGIN_URL)
    page_url = None
    page = None
    try:
        page = item.funcargs.get("page")
        if page is not None:
            page_url = page.url
    except Exception:
        pass

    try:
        from healing.failure_report import capture_from_exception, new_failure_id

        failure_id = new_failure_id()
        screenshot_path = None
        storage_state_path = None
        if page is not None:
            try:
                failures_dir = Path("artifacts/failures")
                failures_dir.mkdir(parents=True, exist_ok=True)
                shot = failures_dir / f"screenshot-{failure_id}.png"
                page.screenshot(path=str(shot))
                screenshot_path = str(shot.resolve())
            except Exception:
                pass
            try:
                failures_dir = Path("artifacts/failures")
                failures_dir.mkdir(parents=True, exist_ok=True)
                state_file = failures_dir / f"storage-state-{failure_id}.json"
                page.context.storage_state(path=str(state_file))
                storage_state_path = str(state_file.resolve())
            except Exception:
                pass

        failure_id, json_path, md_path = capture_from_exception(
            test_nodeid=item.nodeid,
            test_file=str(item.fspath),
            test_name=item.name,
            base_url=base_url,
            page_url=page_url,
            exc=exc,
            step_trace=collector,
            screenshot_path=screenshot_path,
            storage_state_path=storage_state_path,
            failure_id=failure_id,
        )
        print(
            f"\n[healing] failure captured: {failure_id}\n"
            f"  json={json_path}\n  md={md_path}\n"
            f"  next: python -m healing.pom_propose --failure-id {failure_id}\n"
            f"  or: export HEALING_MCP_AUTO=1 to auto-run scan → stub → MCP at session end"
        )
    except Exception as hook_exc:
        print(f"\n[healing] failure capture error: {hook_exc}")


def pytest_addoption(parser):
    parser.addoption(
        "--run-demo-session",
        action="store_true",
        default=False,
        help="Run tests marked demo_session.",
    )
    parser.addoption(
        "--run-healing-demo",
        action="store_true",
        default=False,
        help="Run tests marked healing_demo (opens visible browser with slow-mo).",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-demo-session"):
        skip_demo = pytest.mark.skip(
            reason="Deprecated: use pytest --run-healing-demo tests/test_orangehrm_healing.py"
        )
        for item in items:
            if "demo_session" in item.keywords:
                item.add_marker(skip_demo)

    if not config.getoption("--run-healing-demo"):
        skip_healing = pytest.mark.skip(
            reason="Healing demo only: pytest --run-healing-demo tests/test_orangehrm_healing.py"
        )
        for item in items:
            if "healing_demo" in item.keywords:
                item.add_marker(skip_healing)
