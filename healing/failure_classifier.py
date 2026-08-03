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


def _page_url(payload: dict[str, Any]) -> str:
    env = payload.get("environment") or {}
    return str(env.get("page_url") or env.get("base_url") or "")


def _is_navigation_failure(payload: dict[str, Any]) -> bool:
    ref = str(payload.get("architecture_ref") or "")
    if ref.endswith(".goto") or ref.endswith(".navigate"):
        return True
    failing_step = payload.get("failing_step") or {}
    action = str(failing_step.get("action") or "").lower()
    method = str(failing_step.get("method") or "").lower()
    return action == "navigate" or method == "goto"


def classify_failure(payload: dict[str, Any]) -> str:
    """Return a healing classification for a failure payload."""
    error = payload.get("error") or {}
    exc_type = str(error.get("type", ""))
    message = str(error.get("message", "")).lower()
    traceback_text = str(error.get("traceback", "")).lower()
    combined = f"{exc_type} {message} {traceback_text}"
    page_url = _page_url(payload).lower()

    if _looks_like_auth_failure(payload, combined, page_url):
        return "auth_failure"

    if page_url.startswith("chrome-error:") or "chrome-error://" in page_url:
        return "network"

    if any(re.search(p, combined, re.I) for p in NETWORK_PATTERNS):
        return "network"

    if _is_navigation_failure(payload):
        if "timeout" in combined or exc_type in ("TimeoutError", "Error"):
            return "timeout"
        return "unknown"

    if not payload.get("architecture_ref"):
        return "unknown"

    if any(re.search(p, combined, re.I) for p in TEST_DATA_PATTERNS):
        return "test_data"

    playwright_hint = error.get("playwright_hint")
    has_locator_hint = bool(
        playwright_hint
        or "locator" in combined
        or "get_by_" in combined
        or "timeout" in exc_type.lower()
    )

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


def _looks_like_auth_failure(payload: dict[str, Any], combined: str, page_url: str) -> bool:
    """Session expiry / redirect-to-login — not a locator heal candidate."""
    auth_url_tokens = ("/auth/login", "/login")
    on_login = any(token in page_url for token in auth_url_tokens)
    if page_url.rstrip("/").endswith("saucedemo.com"):
        on_login = True

    auth_msg = any(
        token in combined
        for token in (
            "unauthorized",
            "401",
            "403",
            "session expired",
            "please log in",
            "not authenticated",
            "access denied",
        )
    )

    failing = payload.get("failing_step") or {}
    ref = str(payload.get("architecture_ref") or "")
    post_login_hint = any(
        token in ref.lower() or token in str(failing.get("page_class") or "").lower()
        for token in ("dashboard", "inventory", "pim", "cart", "checkout")
    )

    # Logged-out URL while exercising an authenticated page object.
    if post_login_hint and on_login:
        return True
    if auth_msg and (on_login or post_login_hint):
        return True
    return False


def is_healable(payload: dict[str, Any]) -> bool:
    """True when failure is a candidate for locator repair proposals."""
    return classify_failure(payload) == "selector_break"
