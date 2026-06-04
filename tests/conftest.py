import os
from pathlib import Path

import pytest
from playwright.sync_api import Page

from pages.demo_page import DemoPage
from healing.step_trace import StepTraceCollector, reset_step_trace, set_active_step_trace


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("HEALING_BASE_URL", "https://seleniumbase.io/demo_page")


@pytest.fixture
def demo(page: Page, base_url) -> DemoPage:
    return DemoPage(page, base_url)


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
    base_url = "https://seleniumbase.io/demo_page"
    page_url = None
    screenshot_path = None
    try:
        page = item.funcargs.get("page")
        if page is not None:
            page_url = page.url
            failures_dir = Path("artifacts/failures")
            failures_dir.mkdir(parents=True, exist_ok=True)
            shot = failures_dir / f"screenshot-{item.name}.png"
            page.screenshot(path=str(shot))
            screenshot_path = str(shot.resolve())
    except Exception:
        pass

    try:
        from healing.failure_report import capture_from_exception

        failure_id, json_path, md_path = capture_from_exception(
            test_nodeid=item.nodeid,
            test_file=str(item.fspath),
            test_name=item.name,
            base_url=base_url,
            page_url=page_url,
            exc=exc,
            step_trace=collector,
            screenshot_path=screenshot_path,
        )
        print(
            f"\n[healing] failure captured: {failure_id}\n"
            f"  json={json_path}\n  md={md_path}\n"
            f"  next: python -m healing.pom_propose --failure-id {failure_id}"
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


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-demo-session"):
        return
    skip = pytest.mark.skip(
        reason="Team demo only: pytest --run-demo-session tests/test_demo_total_failure.py"
    )
    for item in items:
        if "demo_session" in item.keywords:
            item.add_marker(skip)
