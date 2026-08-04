"""Shared Playwright timeouts for POM + healing demos."""

from __future__ import annotations

import os


def _env_ms(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


# Navigation can be slow on public demo sites (OrangeHRM / Sauce Demo).
NAV_TIMEOUT_MS = _env_ms("HEALING_NAV_TIMEOUT_MS", 45_000)
# Action timeout for fill/click; keep moderate so intentional broken locators fail promptly.
ACTION_TIMEOUT_MS = _env_ms("HEALING_ACTION_TIMEOUT_MS", 8_000)
# How long to wait for a "page ready" locator after goto.
READY_TIMEOUT_MS = _env_ms("HEALING_READY_TIMEOUT_MS", 30_000)
# Retries for transient net::ERR_* during goto.
NAV_RETRIES = _env_ms("HEALING_NAV_RETRIES", 3)
