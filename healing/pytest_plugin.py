"""Pytest plugin hooks reserved for future POM healing options."""

from __future__ import annotations


def pytest_addoption(parser) -> None:
    group = parser.getgroup("healing", "Playwright healing framework")
    group.addoption(
        "--healing-scan-architecture",
        action="store_true",
        default=False,
        help="Run architecture_scan before tests (optional).",
    )
