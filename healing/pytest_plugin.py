"""Pytest plugin hooks for POM healing automation."""

from __future__ import annotations

from pathlib import Path


def pytest_addoption(parser) -> None:
    group = parser.getgroup("healing", "Playwright healing framework")
    group.addoption(
        "--healing-scan-architecture",
        action="store_true",
        default=False,
        help="Run architecture_scan before tests (optional).",
    )


def pytest_sessionstart(session) -> None:
    from healing.session_state import reset_session_state

    reset_session_state()
    if not session.config.getoption("--healing-scan-architecture"):
        return
    workspace = Path(session.config.rootpath)
    from healing.post_test import run_architecture_scan_if_needed

    run_architecture_scan_if_needed(workspace)


def pytest_sessionfinish(session, exitstatus) -> None:
    workspace = Path(session.config.rootpath)
    from healing.post_test import run_post_test_chain

    run_post_test_chain(workspace)
