"""Base page object with navigation and step tracing for failure reports."""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

from healing.step_trace import record_step


class BasePage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    @property
    def page_class(self) -> str:
        return self.__class__.__name__

    def goto(self) -> None:
        record_step(
            page_class=self.page_class,
            method="goto",
            action="navigate",
            locator_summary=f"goto({self.base_url})",
        )
        self.page.goto(self.base_url)

    def _record(self, method: str, action: str, locator_id: str, locator_summary: str) -> None:
        record_step(
            page_class=self.page_class,
            method=method,
            action=action,
            locator_id=locator_id,
            locator_summary=locator_summary,
        )

    def _click_locator(self, method: str, locator_id: str, locator: Locator) -> None:
        self._record(method, "click", locator_id, locator_summary=locator_id)
        locator.click(timeout=3000)

    def _fill_locator(self, method: str, locator_id: str, locator: Locator, value: str) -> None:
        self._record(method, "fill", locator_id, locator_summary=f"{locator_id}={value!r}")
        locator.fill(value, timeout=3000)

    def _check_locator(self, method: str, locator_id: str, locator: Locator) -> None:
        self._record(method, "check", locator_id, locator_summary=locator_id)
        locator.check(timeout=3000)

    def _uncheck_locator(self, method: str, locator_id: str, locator: Locator) -> None:
        self._record(method, "uncheck", locator_id, locator_summary=locator_id)
        locator.uncheck(timeout=3000)

    def _select_locator(self, method: str, locator_id: str, locator: Locator, value: str) -> None:
        self._record(method, "select_option", locator_id, locator_summary=f"{locator_id}={value!r}")
        locator.select_option(value, timeout=3000)

    def _expect_visible(self, method: str, locator_id: str, locator: Locator) -> None:
        self._record(method, "expect_visible", locator_id, locator_summary=locator_id)
        expect(locator).to_be_visible(timeout=3000)

    def _drag_to(self, method: str, source_id: str, target_id: str, source: Locator, target: Locator) -> None:
        self._record(
            method,
            "drag_to",
            source_id,
            locator_summary=f"{source_id} -> {target_id}",
        )
        source.drag_to(target, timeout=5000)
