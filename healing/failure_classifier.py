"""Classify pytest failures for the healing pipeline."""

from __future__ import annotations

import re
from typing import Any

NETWORK_PATTERNS = (
    r"ERR_INTERNET_DISCONNECTED",
    r"ERR_CONNECTION",
    r"ERR_NETWORK",
    r"ECONNREFUSED",
    r"ENOTFOUND",
    r"net::ERR_",
)

APP_REGRESSION_PATTERNS = (
    r"assertionerror",
    r"expected.*received",
    r"to_be_visible.*timeout",
    r"to_have_text",
    r"to_contain_text",
)

TEST_DATA_PATTERNS = (
    r"fixture.*not found",
    r"no such file",
    r"invalid.*data",
)


def classify_failure(payload: dict[str, Any]) -> str:
    """Return a healing classification for a failure payload."""
    error = payload.get("error") or {}
    exc_type = str(error.get("type", ""))
    message = str(error.get("message", "")).lower()
    traceback_text = str(error.get("traceback", "")).lower()
    combined = f"{exc_type} {message} {traceback_text}"

    if not payload.get("architecture_ref"):
        if any(re.search(p, combined, re.I) for p in NETWORK_PATTERNS):
            return "network"
        return "unknown"

    playwright_hint = error.get("playwright_hint")
    has_locator_hint = bool(
        playwright_hint
        or "locator" in combined
        or "get_by_" in combined
        or "timeout" in exc_type.lower()
    )

    if any(re.search(p, combined, re.I) for p in NETWORK_PATTERNS):
        return "network"

    if any(re.search(p, combined, re.I) for p in TEST_DATA_PATTERNS):
        return "test_data"

    if has_locator_hint or exc_type in ("TimeoutError", "Error"):
        failing_step = payload.get("failing_step") or {}
        if failing_step.get("locator_id"):
            return "selector_break"
        if "timeout" in combined:
            return "timeout"

    if any(re.search(p, combined, re.I) for p in APP_REGRESSION_PATTERNS):
        return "app_regression"

    if has_locator_hint:
        return "selector_break"

    return "unknown"


def is_healable(payload: dict[str, Any]) -> bool:
    """True when failure is a candidate for locator repair proposals."""
    return classify_failure(payload) == "selector_break"
