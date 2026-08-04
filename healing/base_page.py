"""Optional BasePage mixin shipped with the healing package for step tracing."""

from __future__ import annotations

import time

from playwright.sync_api import Error, Locator, Page, expect

from healing.playwright_trace import suppress_auto_trace
from healing.step_trace import record_step
from healing.timeouts import (
    ACTION_TIMEOUT_MS,
    NAV_RETRIES,
    NAV_TIMEOUT_MS,
    READY_TIMEOUT_MS,
)


def _is_transient_navigation_error(exc: BaseException) -> bool:
    message = str(exc)
    return any(
        token in message
        for token in (
            "ERR_NETWORK",
            "ERR_CONNECTION",
            "ERR_INTERNET",
            "ERR_NAME_NOT_RESOLVED",
            "ERR_TIMED_OUT",
            "net::ERR_",
            "Timeout",
            "NS_ERROR_NET",
        )
    )


class BasePage:
    """Playwright page object base with navigation retries and healing step traces.

    Explicit ``record_step`` calls keep rich ``locator_id`` values. Auto-instrumentation
    of Playwright Locator/Page (see ``healing.playwright_trace``) is suppressed around
    the underlying action so steps are not duplicated.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    @property
    def page_class(self) -> str:
        return self.__class__.__name__

    def ready_locator(self) -> Locator | None:
        """Optional locator that must be visible before interacting after goto."""
        return None

    def goto(self) -> None:
        record_step(
            page_class=self.page_class,
            method="goto",
            action="navigate",
            locator_summary=f"goto({self.base_url})",
        )
        last_error: BaseException | None = None
        attempts = max(1, int(NAV_RETRIES))
        for attempt in range(1, attempts + 1):
            try:
                with suppress_auto_trace():
                    self.page.goto(
                        self.base_url,
                        wait_until="domcontentloaded",
                        timeout=NAV_TIMEOUT_MS,
                    )
                    ready = self.ready_locator()
                    if ready is not None:
                        ready.wait_for(state="visible", timeout=READY_TIMEOUT_MS)
                return
            except Error as exc:
                last_error = exc
                if attempt >= attempts or not _is_transient_navigation_error(exc):
                    raise
                time.sleep(0.5 * attempt)
        if last_error is not None:
            raise last_error

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
        with suppress_auto_trace():
            locator.click(timeout=ACTION_TIMEOUT_MS)

    def _fill_locator(self, method: str, locator_id: str, locator: Locator, value: str) -> None:
        self._record(method, "fill", locator_id, locator_summary=f"{locator_id}={value!r}")
        with suppress_auto_trace():
            locator.fill(value, timeout=ACTION_TIMEOUT_MS)

    def _check_locator(self, method: str, locator_id: str, locator: Locator) -> None:
        self._record(method, "check", locator_id, locator_summary=locator_id)
        with suppress_auto_trace():
            locator.check(timeout=ACTION_TIMEOUT_MS)

    def _uncheck_locator(self, method: str, locator_id: str, locator: Locator) -> None:
        self._record(method, "uncheck", locator_id, locator_summary=locator_id)
        with suppress_auto_trace():
            locator.uncheck(timeout=ACTION_TIMEOUT_MS)

    def _select_locator(self, method: str, locator_id: str, locator: Locator, value: str) -> None:
        self._record(method, "select_option", locator_id, locator_summary=f"{locator_id}={value!r}")
        with suppress_auto_trace():
            locator.select_option(value, timeout=ACTION_TIMEOUT_MS)

    def _expect_visible(self, method: str, locator_id: str, locator: Locator) -> None:
        self._record(method, "expect_visible", locator_id, locator_summary=locator_id)
        with suppress_auto_trace():
            expect(locator).to_be_visible(timeout=ACTION_TIMEOUT_MS)

    def _drag_to(
        self,
        method: str,
        source_id: str,
        target_id: str,
        source: Locator,
        target: Locator,
    ) -> None:
        self._record(
            method,
            "drag_to",
            source_id,
            locator_summary=f"{source_id} -> {target_id}",
        )
        with suppress_auto_trace():
            source.drag_to(target, timeout=max(ACTION_TIMEOUT_MS, 5000))
