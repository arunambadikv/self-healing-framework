"""Optional pytest integration: auto-convert raw Playwright tests before collection."""

from __future__ import annotations

import os
from pathlib import Path

from healing.convert_to_smart import auto_convert_policy_violations


def pytest_addoption(parser) -> None:
    group = parser.getgroup("healing", "Playwright healing framework")
    group.addoption(
        "--healing-auto-convert",
        action="store_true",
        default=False,
        help=(
            "Convert test files with raw Playwright selectors to smart.* "
            "(uses locator_registry.yaml). Same as HEALING_AUTO_CONVERT=1."
        ),
    )


def pytest_configure(config) -> None:
    enabled = config.getoption("--healing-auto-convert", default=False)
    if not enabled:
        enabled = os.environ.get("HEALING_AUTO_CONVERT", "").strip() in ("1", "true", "yes")

    if not enabled:
        return

    workspace = Path(config.rootpath)
    changed = auto_convert_policy_violations(
        workspace=workspace,
        apply=True,
    )
    if changed:
        print("\n[healing] auto-converted raw Playwright tests:")
        for path in changed:
            print(f"  - {path.relative_to(workspace)}")
        print()
