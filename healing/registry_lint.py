from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from .registry import lint_registry, validate_registry


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and lint a locator_registry.yaml file."
    )
    parser.add_argument(
        "registry_path",
        nargs="?",
        default="locator_registry.yaml",
        help="Path to locator registry YAML (default: locator_registry.yaml)",
    )
    args = parser.parse_args()
    registry_path = Path(args.registry_path)

    if not registry_path.exists():
        print(f"ERROR: Registry not found: {registry_path}")
        return 2

    registry = _load_yaml(registry_path)
    errors = validate_registry(registry)
    warnings = lint_registry(registry) if isinstance(registry, dict) else []

    if errors:
        print("Registry validation failed:")
        for item in errors:
            print(f"- {item}")
    else:
        print("Registry validation passed.")

    if warnings:
        print("\nRegistry lint warnings:")
        for item in warnings:
            print(f"- {item}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
