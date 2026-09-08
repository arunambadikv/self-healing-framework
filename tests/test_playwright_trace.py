"""Unit tests for package-owned Playwright step auto-instrumentation."""

from __future__ import annotations

from unittest.mock import MagicMock

from pomhealer.playwright_trace import (
    StackFrameInfo,
    attribute_from_frames,
    install_playwright_tracing,
    is_playwright_tracing_installed,
    locator_summary,
    module_stem_to_page_class,
    suppress_auto_trace,
    uninstall_playwright_tracing,
)
from pomhealer.step_trace import (
    StepTraceCollector,
    get_active_step_trace,
    record_step,
    reset_step_trace,
    set_active_step_trace,
)


def test_module_stem_to_page_class():
    assert module_stem_to_page_class("saucedemo_login_page") == "SaucedemoLoginPage"
    assert module_stem_to_page_class("orangehrm_dashboard_page") == "OrangehrmDashboardPage"


def test_attribute_from_frames_pages_method():
    frames = [
        StackFrameInfo(
            filename="/repo/pomhealer/playwright_trace.py",
            function="_auto_record",
            locals={},
        ),
        StackFrameInfo(
            filename="/repo/pages/saucedemo_login_page.py",
            function="click_login",
            locals={"self": type("SauceDemoLoginPage", (), {})()},
        ),
    ]
    attr = attribute_from_frames(frames)
    assert attr.page_class == "SauceDemoLoginPage"
    assert attr.method == "click_login"
    assert attr.locator_id == "click_login"


def test_attribute_from_frames_harvests_base_page_locator_id():
    frames = [
        StackFrameInfo(
            filename="/repo/pomhealer/playwright_trace.py",
            function="wrapped",
            locals={},
        ),
        StackFrameInfo(
            filename="/repo/pomhealer/base_page.py",
            function="_click_locator",
            locals={"locator_id": "login_button", "method": "click_login"},
        ),
        StackFrameInfo(
            filename="/repo/pages/orangehrm_login_page.py",
            function="click_login",
            locals={"self": type("OrangeHrmLoginPage", (), {})()},
        ),
    ]
    attr = attribute_from_frames(frames)
    assert attr.page_class == "OrangeHrmLoginPage"
    assert attr.method == "click_login"
    assert attr.locator_id == "login_button"


def test_attribute_from_frames_unknown_without_pages():
    frames = [
        StackFrameInfo(
            filename="/repo/tests/test_foo.py",
            function="test_login",
            locals={},
        ),
    ]
    attr = attribute_from_frames(frames)
    assert attr.page_class == "UnknownPage"
    assert attr.method == "unknown"


def _noop_playwright_originals() -> None:
    """Replace stored Playwright originals so unit tests never hit a real browser."""
    import pomhealer.playwright_trace as pt

    for key in list(pt._originals):
        pt._originals[key] = lambda self, *args, **kwargs: None


def _restore_playwright_tracing() -> None:
    uninstall_playwright_tracing()
    install_playwright_tracing()


def test_suppress_auto_trace_skips_instrumentation():
    uninstall_playwright_tracing()
    assert install_playwright_tracing()
    _noop_playwright_originals()
    collector = StepTraceCollector(test_name="t", test_module="m")
    token = set_active_step_trace(collector)
    try:
        from playwright.sync_api import Locator

        with suppress_auto_trace():
            # Call patched method with a mock self — should not record.
            Locator.click(MagicMock(), timeout=1)
        assert collector.steps == []

        # Without suppress, patched click records (UnknownPage if not under pages/).
        Locator.click(MagicMock(), timeout=1)
        assert len(collector.steps) == 1
        assert collector.steps[0].action == "click"
    finally:
        reset_step_trace(token)
        _restore_playwright_tracing()


def test_raw_page_method_click_records_from_stack():
    """Consumer-style POM: property + locator.click() without BasePage helpers."""
    import types
    from pathlib import Path

    uninstall_playwright_tracing()
    assert install_playwright_tracing()
    _noop_playwright_originals()
    collector = StepTraceCollector(test_name="t", test_module="m")
    token = set_active_step_trace(collector)
    try:
        from pages.saucedemo_login_page import SauceDemoLoginPage
        from playwright.sync_api import Locator

        page = MagicMock()
        pages_file = str(Path(__file__).resolve().parents[1] / "pages" / "saucedemo_login_page.py")

        def _click_login_raw(self):
            Locator.click(MagicMock(), timeout=1)

        # Attribute stack uses co_filename; bind a copy that looks like it lives under pages/.
        code = _click_login_raw.__code__.replace(
            co_filename=pages_file,
            co_name="click_login_raw",
        )
        bound = types.FunctionType(
            code,
            _click_login_raw.__globals__,
            "click_login_raw",
            _click_login_raw.__defaults__,
            _click_login_raw.__closure__,
        )
        SauceDemoLoginPage.click_login_raw = bound  # type: ignore[attr-defined]
        login = SauceDemoLoginPage(page, "https://www.saucedemo.com/")
        login.click_login_raw()  # type: ignore[attr-defined]

        assert len(collector.steps) == 1
        step = collector.steps[0]
        assert step.page_class == "SauceDemoLoginPage"
        assert step.method == "click_login_raw"
        assert step.action == "click"
    finally:
        reset_step_trace(token)
        if hasattr(SauceDemoLoginPage, "click_login_raw"):
            delattr(SauceDemoLoginPage, "click_login_raw")
        _restore_playwright_tracing()


def test_base_page_helper_does_not_double_record():
    uninstall_playwright_tracing()
    assert install_playwright_tracing()
    _noop_playwright_originals()
    collector = StepTraceCollector(test_name="t", test_module="m")
    token = set_active_step_trace(collector)
    try:
        from pages.saucedemo_login_page import SauceDemoLoginPage
        from playwright.sync_api import Locator

        page = MagicMock()
        locator = MagicMock()
        # Route through patched Locator.click so suppress_auto_trace is exercised.
        locator.click = lambda **kwargs: Locator.click(MagicMock(), **kwargs)

        login = SauceDemoLoginPage(page, "https://www.saucedemo.com/")
        login._click_locator("click_login", "login_button", locator)

        assert len(collector.steps) == 1
        step = collector.steps[0]
        assert step.locator_id == "login_button"
        assert step.method == "click_login"
        assert step.action == "click"
    finally:
        reset_step_trace(token)
        _restore_playwright_tracing()


def test_locator_summary_truncates():
    long = "x" * 200
    summary = locator_summary(long, action="click")
    assert summary.startswith("click:")
    assert len(summary) <= 170


def test_install_idempotent_and_uninstall():
    uninstall_playwright_tracing()
    assert install_playwright_tracing() is True
    assert is_playwright_tracing_installed()
    assert install_playwright_tracing() is True
    uninstall_playwright_tracing()
    assert not is_playwright_tracing_installed()
    # Leave installed for the rest of the pytest session (plugin expectation).
    install_playwright_tracing()


def test_record_step_noop_without_collector():
    token = set_active_step_trace(None)
    try:
        assert get_active_step_trace() is None
        record_step(page_class="P", method="m", action="click")
    finally:
        reset_step_trace(token)
