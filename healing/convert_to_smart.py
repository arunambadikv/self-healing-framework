from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from healing.ci_gates import load_gate_config
from healing.test_policy import list_raw_test_files


@dataclass
class Replacement:
    line_no: int
    old: str
    new: str
    note: str


def _load_registry(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registry root must be a mapping.")
    return data


def _build_index(registry: dict[str, Any]) -> dict[tuple[Any, ...], list[str]]:
    """
    Index locator candidates -> semantic keys.
    We index preferred + fallback candidates.
    """
    index: dict[tuple[Any, ...], list[str]] = {}
    for key, entry in registry.items():
        candidates = list(entry.get("preferred", [])) + list(entry.get("fallback", []))
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            ctype = candidate.get("type")
            signature: tuple[Any, ...] | None = None
            if ctype == "css":
                signature = ("css", candidate.get("value"))
            elif ctype == "text":
                signature = ("text", candidate.get("value"), bool(candidate.get("exact", False)))
            elif ctype == "placeholder":
                signature = ("placeholder", candidate.get("value"))
            elif ctype == "role":
                signature = ("role", candidate.get("role"), candidate.get("name"))
            elif ctype == "label":
                signature = ("label", candidate.get("value"))
            elif ctype == "test_id":
                signature = ("test_id", candidate.get("value"))
            if signature is None:
                continue
            index.setdefault(signature, []).append(key)
    return index


def _pick_key(
    *,
    candidates: list[str],
    registry: dict[str, Any],
    expected_action: str,
) -> tuple[str | None, str]:
    if not candidates:
        return None, "no matching semantic key in registry"

    # Prefer keys whose declared action matches.
    action_matches = [k for k in candidates if registry.get(k, {}).get("action") == expected_action]
    if len(action_matches) == 1:
        return action_matches[0], "matched by action + locator"
    if len(action_matches) > 1:
        return None, f"ambiguous keys for action '{expected_action}': {action_matches}"

    if len(candidates) == 1:
        return candidates[0], "matched by locator (action differs)"
    return None, f"ambiguous keys for locator: {candidates}"


def _ensure_smart_param(lines: list[str]) -> list[str]:
    updated = lines[:]
    func_def = re.compile(r"^(\s*)def\s+(test_[A-Za-z0-9_]+)\((.*?)\):\s*$")
    for idx, line in enumerate(updated):
        match = func_def.match(line)
        if not match:
            continue
        indent, _, args = match.groups()
        arg_items = [item.strip() for item in args.split(",") if item.strip()]
        if "smart" not in arg_items:
            arg_items.append("smart")
            updated[idx] = f"{indent}def {match.group(2)}({', '.join(arg_items)}):"
    return updated


def convert_file(registry_path: Path, test_file: Path) -> tuple[list[str], list[Replacement]]:
    registry = _load_registry(registry_path)
    index = _build_index(registry)
    lines = test_file.read_text(encoding="utf-8").splitlines()
    lines = _ensure_smart_param(lines)

    patterns: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(r'^(?P<indent>\s*)page\.locator\("(?P<css>[^"]+)"\)\.click\(\)\s*$'),
            "click",
            'smart.click("{key}")',
        ),
        (
            re.compile(r'^(?P<indent>\s*)page\.locator\("(?P<css>[^"]+)"\)\.fill\("(?P<value>[^"]*)"\)\s*$'),
            "fill",
            'smart.fill("{key}", "{value}")',
        ),
        (
            re.compile(r'^(?P<indent>\s*)page\.locator\("(?P<css>[^"]+)"\)\.check\(\)\s*$'),
            "check",
            'smart.check("{key}")',
        ),
        (
            re.compile(r'^(?P<indent>\s*)page\.locator\("(?P<css>[^"]+)"\)\.uncheck\(\)\s*$'),
            "uncheck",
            'smart.uncheck("{key}")',
        ),
        (
            re.compile(
                r'^(?P<indent>\s*)expect\(page\.locator\("(?P<css>[^"]+)"\)\)\.to_be_visible\(\)\s*$'
            ),
            "expect_visible",
            'smart.expect_visible("{key}")',
        ),
        (
            re.compile(
                r'^(?P<indent>\s*)page\.get_by_placeholder\("(?P<placeholder>[^"]+)"\)\.fill\("(?P<value>[^"]*)"\)\s*$'
            ),
            "fill",
            'smart.fill("{key}", "{value}")',
        ),
        (
            re.compile(
                r'^(?P<indent>\s*)page\.get_by_text\("(?P<text>[^"]+)"\)\.click\(\)\s*$'
            ),
            "click",
            'smart.click("{key}")',
        ),
        (
            re.compile(
                r'^(?P<indent>\s*)expect\(page\.get_by_text\("(?P<text>[^"]+)"\)\)\.to_be_visible\(\)\s*$'
            ),
            "expect_visible",
            'smart.expect_visible("{key}")',
        ),
        (
            re.compile(
                r'^(?P<indent>\s*)page\.get_by_role\(\s*"(?P<role>[^"]+)"\s*,\s*'
                r'name\s*=\s*"(?P<name>[^"]+)"(?:\s*,\s*exact\s*=\s*True)?\s*\)\.click\(\)\s*$'
            ),
            "click",
            'smart.click("{key}")',
        ),
        (
            re.compile(
                r'^(?P<indent>\s*)expect\(page\.get_by_role\(\s*"(?P<role>[^"]+)"\s*,\s*'
                r'name\s*=\s*"(?P<name>[^"]+)"(?:\s*,\s*exact\s*=\s*True)?\s*\)\)\.to_be_visible\(\)\s*$'
            ),
            "expect_visible",
            'smart.expect_visible("{key}")',
        ),
    ]

    replacements: list[Replacement] = []
    converted = lines[:]
    for i, line in enumerate(lines):
        replaced = False
        for regex, action, template in patterns:
            match = regex.match(line)
            if not match:
                continue
            groups = match.groupdict()
            indent = groups.get("indent", "")

            if "css" in groups:
                signature = ("css", groups["css"])
            elif "text" in groups:
                signature = ("text", groups["text"], False)
            elif "placeholder" in groups:
                signature = ("placeholder", groups["placeholder"])
            elif "role" in groups and "name" in groups:
                signature = ("role", groups["role"], groups["name"])
            else:
                signature = ("",)

            key, note = _pick_key(
                candidates=index.get(signature, []),
                registry=registry,
                expected_action=action,
            )

            if key is None:
                converted[i] = f'{indent}# TODO(convert_to_smart): {note}\n{line}'.rstrip("\n")
                replacements.append(
                    Replacement(i + 1, line, converted[i], f"unconverted: {note}")
                )
                replaced = True
                break

            new_line = template.format(key=key, **groups)
            converted[i] = indent + new_line
            replacements.append(
                Replacement(i + 1, line, converted[i], f"converted using key '{key}'")
            )
            replaced = True
            break

        if replaced:
            continue

    return converted, replacements


def _cleanup_playwright_only_imports(lines: list[str]) -> list[str]:
    """Drop sync_api imports when no raw page.* / expect(page.*) calls remain."""
    body = "\n".join(lines)
    if re.search(r"\bpage\.(locator|get_by_)", body) or re.search(r"expect\(page\.", body):
        return lines
    cleaned: list[str] = []
    for line in lines:
        if re.match(r"^\s*from playwright\.sync_api import\b", line):
            continue
        cleaned.append(re.sub(r":\s*Page\b", "", line))
    return cleaned


@dataclass
class ConvertResult:
    path: Path
    replacements: list[Replacement]
    applied: bool
    has_todos: bool


def convert_test_file(
    *,
    registry_path: Path,
    test_file: Path,
    apply: bool,
) -> ConvertResult:
    converted, replacements = convert_file(registry_path=registry_path, test_file=test_file)
    converted = _cleanup_playwright_only_imports(converted)
    has_todos = any("TODO(convert_to_smart)" in line for line in converted)
    if apply and replacements:
        test_file.write_text("\n".join(converted) + "\n", encoding="utf-8")
    return ConvertResult(
        path=test_file,
        replacements=replacements,
        applied=apply and bool(replacements),
        has_todos=has_todos,
    )


def auto_convert_policy_violations(
    *,
    workspace: Path,
    tests_dir: Path | None = None,
    registry_path: Path | None = None,
    config_path: Path | None = None,
    apply: bool = True,
) -> list[Path]:
    """
    Find tests that violate test_policy and convert registry-mappable lines to smart.*.
    Returns paths of files written when apply=True.
    """
    tests_dir = tests_dir or workspace / "tests"
    registry_path = registry_path or workspace / "locator_registry.yaml"
    config_path = config_path or workspace / "healing" / "ci_gates_config.yaml"

    allowlist: list[Path] = []
    forbidden: list[str] | None = None
    if config_path.exists():
        gate_config = load_gate_config(config_path)
        allowlist = [workspace / p for p in gate_config.test_policy_allowlist]
        forbidden = gate_config.test_policy_forbidden_patterns or None

    changed: list[Path] = []
    for test_file in list_raw_test_files(
        tests_dir=tests_dir,
        allowlist=allowlist,
        forbidden_patterns=forbidden,
        workspace=workspace,
    ):
        result = convert_test_file(
            registry_path=registry_path,
            test_file=test_file,
            apply=apply,
        )
        if result.applied:
            changed.append(test_file)
    return changed


def _print_result(result: ConvertResult, *, dry_run: bool) -> None:
    rel = result.path
    if not result.replacements:
        print(f"{rel}: no registry-mappable lines (manual conversion may still be required).")
        return
    print(f"{rel}: {len(result.replacements)} line(s)")
    for item in result.replacements:
        print(f"  L{item.line_no}: {item.note}")
        print(f"    old: {item.old}")
        print(f"    new: {item.new}")
    if result.has_todos:
        print("  WARNING: file contains TODO(convert_to_smart) — finish manually.")
    if dry_run:
        print("  (dry-run; use --apply to write)")
    elif result.applied:
        print(f"  updated: {rel}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert raw Playwright test statements to SmartPage semantic-key calls. "
            "Dry-run by default."
        )
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", help="Path to a single test file to convert.")
    target.add_argument(
        "--scan-tests",
        action="store_true",
        help="Convert all test_*.py files that violate test_policy (see ci_gates_config.yaml).",
    )
    parser.add_argument(
        "--registry",
        default="locator_registry.yaml",
        help="Path to locator registry YAML (default: locator_registry.yaml).",
    )
    parser.add_argument(
        "--config",
        default="healing/ci_gates_config.yaml",
        help="CI gates config for test_policy allowlist (default: healing/ci_gates_config.yaml).",
    )
    parser.add_argument(
        "--tests-dir",
        default="tests",
        help="Tests directory for --scan-tests (default: tests).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes back to file(s). Without this flag, prints preview only.",
    )
    args = parser.parse_args()

    workspace = Path.cwd()
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = workspace / registry_path
    if not registry_path.exists():
        print(f"ERROR: registry file not found: {registry_path}")
        return 2

    if args.scan_tests:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = workspace / config_path
        tests_dir = Path(args.tests_dir)
        if not tests_dir.is_absolute():
            tests_dir = workspace / tests_dir

        allowlist: list[Path] = []
        forbidden: list[str] | None = None
        if config_path.exists():
            gate_config = load_gate_config(config_path)
            allowlist = [workspace / p for p in gate_config.test_policy_allowlist]
            forbidden = gate_config.test_policy_forbidden_patterns or None

        raw_files = list_raw_test_files(
            tests_dir=tests_dir,
            allowlist=allowlist,
            forbidden_patterns=forbidden,
            workspace=workspace,
        )
        if not raw_files:
            print("No raw Playwright test files found (test_policy clean).")
            return 0

        print(f"Found {len(raw_files)} file(s) with raw Playwright selectors:")
        exit_code = 0
        for test_file in raw_files:
            result = convert_test_file(
                registry_path=registry_path,
                test_file=test_file,
                apply=args.apply,
            )
            _print_result(result, dry_run=not args.apply)
            if result.has_todos:
                exit_code = 1
        if not args.apply:
            print("\nDry-run only. Re-run with --scan-tests --apply to persist all changes.")
        return exit_code

    test_file = Path(args.file)
    if not test_file.is_absolute():
        test_file = workspace / test_file
    if not test_file.exists():
        print(f"ERROR: test file not found: {test_file}")
        return 2

    result = convert_test_file(
        registry_path=registry_path,
        test_file=test_file,
        apply=args.apply,
    )
    if not result.replacements:
        print("No convertible raw Playwright patterns found.")
        return 0

    _print_result(result, dry_run=not args.apply)
    return 1 if result.has_todos else 0


if __name__ == "__main__":
    raise SystemExit(main())
