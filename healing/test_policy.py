from __future__ import annotations

import re
from pathlib import Path


DEFAULT_FORBIDDEN = [
    r"page\.locator\(",
    r"page\.get_by_[a-z_]+\(",
    r"expect\(page\.",
]

DEFAULT_REQUIRE_SMART = [
    r"smart\.(click|fill|check|uncheck|select_option|expect_visible|expect_text|drag_to)\(",
]


def _normalize_allowlist(paths: list[Path], workspace: Path) -> set[Path]:
    allowed: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if not path.is_absolute():
            resolved = (workspace / path).resolve()
        allowed.add(resolved)
    return allowed


def check_test_policy(
    *,
    tests_dir: Path,
    allowlist: list[Path],
    forbidden_patterns: list[str] | None = None,
    require_smart_fixture: bool = True,
    workspace: Path | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if workspace is None:
        workspace = tests_dir.parent

    patterns = forbidden_patterns or DEFAULT_FORBIDDEN
    compiled = [re.compile(p) for p in patterns]
    smart_action = re.compile(DEFAULT_REQUIRE_SMART[0])

    allowed_files = _normalize_allowlist(allowlist, workspace)

    if not tests_dir.exists():
        errors.append(f"Tests directory not found: {tests_dir}")
        return errors, warnings

    for test_file in sorted(tests_dir.glob("test_*.py")):
        if test_file.resolve() in allowed_files:
            continue

        content = test_file.read_text(encoding="utf-8")
        rel = test_file.relative_to(workspace)

        for pattern in compiled:
            if pattern.search(content):
                errors.append(
                    f"{rel}: raw Playwright selector detected ({pattern.pattern}). "
                    "Use smart.* semantic keys or add file to test_policy.allowlist."
                )
                break

        if require_smart_fixture and smart_action.search(content):
            if "def test_" in content and "smart" not in content:
                errors.append(
                    f"{rel}: uses smart.* but test signature missing `smart` fixture."
                )

    return errors, warnings


def list_raw_test_files(
    *,
    tests_dir: Path,
    allowlist: list[Path],
    forbidden_patterns: list[str] | None = None,
    workspace: Path | None = None,
) -> list[Path]:
    """Return test files that contain forbidden raw Playwright selector patterns."""
    if workspace is None:
        workspace = tests_dir.parent

    patterns = forbidden_patterns or DEFAULT_FORBIDDEN
    compiled = [re.compile(p) for p in patterns]
    allowed_files = _normalize_allowlist(allowlist, workspace)
    raw_files: list[Path] = []

    if not tests_dir.exists():
        return raw_files

    for test_file in sorted(tests_dir.glob("test_*.py")):
        if test_file.resolve() in allowed_files:
            continue
        content = test_file.read_text(encoding="utf-8")
        if any(pattern.search(content) for pattern in compiled):
            raw_files.append(test_file)

    return raw_files
