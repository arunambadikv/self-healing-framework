from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from healing.apply_suggestion import _load_registry, _save_registry
from healing.registry import validate_registry
from healing.resolved_apply import apply_proposal_to_registry, extract_proposal


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply agent/MCP-reviewed repair from artifacts/mcp-repair-bundles/resolved/"
    )
    parser.add_argument("--key", help="Semantic key to apply.")
    parser.add_argument(
        "--apply-all",
        action="store_true",
        help="Apply every *.json file in the resolved directory.",
    )
    parser.add_argument(
        "--resolved-dir",
        default="artifacts/mcp-repair-bundles/resolved",
        help="Directory containing agent-written resolved JSON files.",
    )
    parser.add_argument("--registry", default="locator_registry.yaml")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write registry. Default is dry-run.",
    )
    args = parser.parse_args()
    if not args.apply_all and not args.key:
        parser.error("Provide --key or --apply-all.")

    resolved_dir = Path(args.resolved_dir)
    registry_path = Path(args.registry)

    if args.apply_all:
        if not resolved_dir.exists():
            print(f"No resolved directory: {resolved_dir}")
            return 0
        files = sorted(resolved_dir.glob("*.json"))
        if not files:
            print(f"No resolved JSON files in {resolved_dir}")
            return 0
        exit_code = 0
        registry = _load_registry(registry_path)
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            proposal = payload.get("proposal") or payload
            semantic_key = proposal.get("semantic_key", path.stem)
            try:
                message = apply_proposal_to_registry(registry, payload)
                print(f"[ok] {semantic_key}: {message}")
            except ValueError as exc:
                print(f"[skip] {path.name}: {exc}")
                exit_code = 1
                continue
        errors = validate_registry(registry)
        if errors:
            print("ERROR: registry invalid after apply-all:")
            for err in errors:
                print(f"- {err}")
            return 1
        if args.apply:
            _save_registry(registry_path, registry)
            print(f"Registry updated: {registry_path} ({len(files)} file(s) processed)")
        else:
            print("Dry-run only. Re-run with --apply-all --apply to persist.")
        return exit_code

    slug = args.key.replace(".", "_")
    candidates = sorted(resolved_dir.glob(f"{slug}*.json")) + sorted(
        resolved_dir.glob(f"{args.key}*.json")
    )
    if not candidates:
        print(f"ERROR: no resolved file for key '{args.key}' in {resolved_dir}")
        print("Agent should write: artifacts/mcp-repair-bundles/resolved/<key>.json")
        return 1

    payload = json.loads(candidates[0].read_text(encoding="utf-8"))
    registry_path = Path(args.registry)
    registry = _load_registry(registry_path)

    message = apply_proposal_to_registry(registry, payload)
    errors = validate_registry(registry)
    if errors:
        print("ERROR: registry invalid after apply:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(message)
    if args.apply:
        _save_registry(registry_path, registry)
        print(f"Registry updated: {registry_path}")
        cmd = (payload.get("proposal") or payload).get("validation_command")
        if cmd:
            print(f"Run validation: {cmd}")
    else:
        print("Dry-run only. Re-run with --apply to persist.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
