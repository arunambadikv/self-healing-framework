"""Pytest plugin hooks for POM healing automation (capture + session chain)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from healing.step_trace import StepTraceCollector, reset_step_trace, set_active_step_trace


def pytest_addoption(parser) -> None:
    group = parser.getgroup("healing", "Playwright healing framework")
    group.addoption(
        "--healing-scan-architecture",
        action="store_true",
        default=False,
        help="Run architecture_scan before tests (optional).",
    )
    group.addoption(
        "--run-demo-session",
        action="store_true",
        default=False,
        help="Run tests marked demo_session.",
    )
    group.addoption(
        "--run-healing-demo",
        action="store_true",
        default=False,
        help="Run tests marked healing_demo (opens browser; set HEALING_DEMO_HEADLESS=1 for CI).",
    )


def pytest_configure(config) -> None:
    from healing.doctor import load_dotenv_files
    from healing.paths import configure_workspace
    from healing.playwright_trace import install_playwright_tracing

    workspace = Path(config.rootpath)
    configure_workspace(workspace)
    load_dotenv_files(workspace)
    # Patch Playwright Locator/Page so consumer POMs get test_steps without BasePage helpers.
    install_playwright_tracing()


def pytest_sessionstart(session) -> None:
    from healing.auto_scan import run_auto_architecture_discovery
    from healing.paths import configure_workspace
    from healing.playwright_trace import install_playwright_tracing
    from healing.session_state import reset_session_state

    workspace = Path(session.config.rootpath)
    configure_workspace(workspace)
    reset_session_state()
    install_playwright_tracing()
    # After pip install/update (or stale pages), refresh architecture automatically.
    force = bool(session.config.getoption("--healing-scan-architecture"))
    run_auto_architecture_discovery(workspace, force=force)


def pytest_sessionfinish(session, exitstatus) -> None:
    workspace = Path(session.config.rootpath)
    from healing.post_test import run_post_test_chain
    from healing.playwright_trace import uninstall_playwright_tracing

    try:
        run_post_test_chain(workspace)
    finally:
        uninstall_playwright_tracing()


def pytest_collection_modifyitems(config, items) -> None:
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


@pytest.fixture(autouse=True)
def _healing_step_trace(request):
    collector = StepTraceCollector(
        test_name=request.node.name,
        test_module=Path(str(request.node.fspath)).stem,
    )
    token = set_active_step_trace(collector)
    request.node._healing_step_trace = collector  # type: ignore[attr-defined]
    yield
    reset_step_trace(token)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture healable failures into healer-artifacts/failures."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or report.passed:
        return

    exc = call.excinfo.value if call.excinfo else None
    if exc is None:
        return

    collector = getattr(item, "_healing_step_trace", None)
    base_url = os.environ.get("HEALING_BASE_URL", "")
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
        from healing.paths import FAILURES_DIR, ensure_queue_dirs

        ensure_queue_dirs()
        failure_id = new_failure_id(item.name)
        screenshot_path = None
        storage_state_path = None
        if page is not None:
            try:
                shot = FAILURES_DIR / f"screenshot-{failure_id}.png"
                page.screenshot(path=str(shot))
                screenshot_path = str(Path(shot).resolve())
            except Exception:
                pass
            try:
                state_file = FAILURES_DIR / f"storage-state-{failure_id}.json"
                page.context.storage_state(path=str(state_file))
                storage_state_path = str(Path(state_file).resolve())
            except Exception:
                pass

        if not base_url:
            try:
                base_url = item.funcargs.get("base_url") or ""
            except Exception:
                base_url = ""

        failure_id, json_path, md_path = capture_from_exception(
            test_nodeid=item.nodeid,
            test_file=str(item.fspath),
            test_name=item.name,
            base_url=str(base_url),
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
            f"  or: set HEALING_MCP_AUTO=1 in .env (or export) to auto-run scan → stub → MCP at session end"
        )
    except Exception as hook_exc:
        print(f"\n[healing] failure capture error: {hook_exc}")
