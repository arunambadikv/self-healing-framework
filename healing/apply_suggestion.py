from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from healing.registry import validate_registry
from healing.registry_updater import suggest_registry_updates


def _candidate_equal(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return left == right


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _apply_promote_fallback(registry: dict[str, Any], key: str, candidate: dict[str, Any]) -> str:
    if key not in registry:
        raise ValueError(f"Cannot promote fallback for missing key '{key}'.")

    entry = registry[key]
    preferred = _ensure_list(entry.get("preferred"))
    fallback = _ensure_list(entry.get("fallback"))

    if any(_candidate_equal(item, candidate) for item in preferred):
        return f"No change: candidate already present in '{key}.preferred'."

    # Promote candidate to top priority.
    preferred.insert(0, candidate)
    fallback = [item for item in fallback if not _candidate_equal(item, candidate)]
    entry["preferred"] = preferred
    entry["fallback"] = fallback
    return f"Promoted candidate to '{key}.preferred[0]' and removed duplicate from fallback."


def _apply_add_semantic_key(
    registry: dict[str, Any], key: str, suggested_entry: dict[str, Any]
) -> str:
    if key in registry:
        raise ValueError(f"Cannot add key '{key}' because it already exists.")
    if not isinstance(suggested_entry, dict):
        raise ValueError("Suggested entry for add_semantic_key must be a mapping.")

    registry[key] = suggested_entry
    return f"Added new semantic key '{key}' from reviewed suggestion."


def _load_registry(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registry root must be a mapping.")
    return data


def _save_registry(path: Path, registry: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply one reviewed registry suggestion from a healing report. "
            "Dry-run by default; pass --apply to write."
        )
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Path to healing report JSON (e.g. artifacts/healing-reports/test_x.json).",
    )
    parser.add_argument(
        "--key",
        required=True,
        help="Semantic key to apply (e.g. demo.green_button).",
    )
    parser.add_argument(
        "--change-type",
        choices=["promote_fallback", "add_semantic_key"],
        help="Optional change type filter if the key has multiple suggestions.",
    )
    parser.add_argument(
        "--registry",
        default="locator_registry.yaml",
        help="Registry YAML path (default: locator_registry.yaml).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes to registry. Without this flag, command is dry-run.",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    registry_path = Path(args.registry)
    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}")
        return 2
    if not registry_path.exists():
        print(f"ERROR: registry not found: {registry_path}")
        return 2

    suggestions = suggest_registry_updates(report_path)
    selected = [
        item
        for item in suggestions
        if item.semantic_key == args.key
        and (args.change_type is None or item.change_type == args.change_type)
    ]
    if not selected:
        print(
            "ERROR: no matching suggestion found. "
            "Check --key/--change-type and ensure the report has relevant events."
        )
        return 1
    if len(selected) > 1:
        print("ERROR: multiple suggestions matched. Pass --change-type to disambiguate.")
        for item in selected:
            print(f"- {item.semantic_key}: {item.change_type}")
        return 1

    suggestion = selected[0]
    registry = _load_registry(registry_path)

    if suggestion.change_type == "promote_fallback":
        candidate = suggestion.suggested_candidate
        if not isinstance(candidate, dict):
            print("ERROR: promote_fallback suggestion has no valid candidate.")
            return 1
        message = _apply_promote_fallback(registry, suggestion.semantic_key, candidate)
    elif suggestion.change_type == "add_semantic_key":
        candidate = suggestion.suggested_candidate
        if not isinstance(candidate, dict):
            print("ERROR: add_semantic_key suggestion has no valid entry.")
            return 1
        message = _apply_add_semantic_key(registry, suggestion.semantic_key, candidate)
    else:
        print(f"ERROR: unsupported change_type '{suggestion.change_type}'.")
        return 1

    errors = validate_registry(registry)
    if errors:
        print("ERROR: refusing to proceed because updated registry is invalid:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(f"Suggestion: {suggestion.semantic_key} [{suggestion.change_type}]")
    print(message)
    if args.apply:
        _save_registry(registry_path, registry)
        print(f"Registry updated: {registry_path}")
    else:
        print("Dry-run only. Re-run with --apply to persist.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
