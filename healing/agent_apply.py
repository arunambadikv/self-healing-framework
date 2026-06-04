"""Apply approved Phase C resolved proposals to locator_registry.yaml."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from healing.approval_manifest import _load_manifest, approved_entries
from healing.apply_suggestion import _load_registry, _save_registry
from healing.registry import validate_registry
from healing.resolved_apply import apply_proposal_to_registry


def apply_approved_proposals(
    *,
    manifest_path: Path,
    registry_path: Path,
    apply: bool,
    require_validation_pass: bool,
) -> tuple[int, list[str]]:
    manifest = _load_manifest(manifest_path)
    registry = _load_registry(registry_path)
    messages: list[str] = []
    applied = 0
    exit_code = 0

    for entry in approved_entries(manifest):
        semantic_key = entry.get("semantic_key")
        resolved_file = Path(entry.get("resolved_file", ""))
        if not resolved_file.exists():
            messages.append(f"[skip] {semantic_key}: missing resolved file")
            exit_code = 1
            continue

        if require_validation_pass and not entry.get("validation_passed"):
            messages.append(f"[skip] {semantic_key}: validation did not pass")
            exit_code = 1
            continue

        payload = json.loads(resolved_file.read_text(encoding="utf-8"))
        try:
            message = apply_proposal_to_registry(registry, payload)
            messages.append(f"[ok] {semantic_key}: {message}")
            applied += 1
        except ValueError as exc:
            messages.append(f"[skip] {semantic_key}: {exc}")
            exit_code = 1

    errors = validate_registry(registry)
    if errors:
        for err in errors:
            messages.append(f"[registry-error] {err}")
        return applied, messages

    if apply and applied:
        _save_registry(registry_path, registry)
        messages.append(f"Registry updated: {registry_path} ({applied} approved proposal(s))")
    elif not apply and applied:
        messages.append("Dry-run only. Re-run with --apply to persist.")

    return applied, messages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply manifest-approved resolved proposals to locator_registry.yaml."
    )
    parser.add_argument(
        "--manifest",
        default="artifacts/agent-proposals-resolved/approval-manifest.json",
        help="Approval manifest path.",
    )
    parser.add_argument("--registry", default="locator_registry.yaml")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write registry. Default is dry-run.",
    )
    parser.add_argument(
        "--require-validation-pass",
        action="store_true",
        default=True,
        help="Only apply entries with validation_passed=true (default: true).",
    )
    parser.add_argument(
        "--allow-failed-validation",
        action="store_true",
        help="Apply approved entries even when validation_passed is false.",
    )
    args = parser.parse_args()

    applied, messages = apply_approved_proposals(
        manifest_path=Path(args.manifest),
        registry_path=Path(args.registry),
        apply=args.apply,
        require_validation_pass=not args.allow_failed_validation,
    )
    for line in messages:
        print(line)

    if any(line.startswith("[registry-error]") for line in messages):
        return 1
    if applied == 0:
        return 1
    if any(line.startswith("[skip]") for line in messages):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
