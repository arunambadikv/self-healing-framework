"""Apply healing-queue POM patches to pages/*.py."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _allowed_file(path: Path, workspace: Path) -> bool:
    rel = path.resolve().relative_to(workspace.resolve())
    parts = rel.parts
    return len(parts) >= 2 and parts[0] == "pages" and path.suffix == ".py"


def apply_architecture_update(
    workspace: Path,
    update: dict[str, Any],
    *,
    dry_run: bool = False,
) -> str:
    file_path = workspace / update["file"]
    if not _allowed_file(file_path, workspace):
        raise ValueError(f"Refusing to edit outside pages/: {update['file']}")

    if not file_path.exists():
        raise FileNotFoundError(f"Page file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    before = update.get("before", "")
    after = update.get("after", "")
    symbol = update.get("symbol", "")

    new_content = content
    message = ""

    if before and after and before in content:
        new_content = content.replace(before, after, 1)
        message = f"Replaced locator expression for '{symbol}' in {update['file']}"
    elif symbol and after:
        # Replace return line inside @property def symbol
        pattern = rf"(@property\s+def\s+{re.escape(symbol)}\s*\([^)]*\)\s*->[^:]+:\s*\n\s*return\s+)(.+)"
        match = re.search(pattern, content)
        if match:
            new_content = content[: match.start(2)] + after + content[match.end(2) :]
            message = f"Updated property '{symbol}' return in {update['file']}"
        else:
            raise ValueError(f"Could not locate property '{symbol}' in {update['file']}")
    else:
        raise ValueError(f"Insufficient update data for symbol '{symbol}'")

    if new_content == content:
        raise ValueError(f"No changes applied for '{symbol}'")

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")
    return message


def apply_patch_payload(
    payload: dict[str, Any],
    *,
    workspace: Path,
    dry_run: bool = False,
    run_validation: bool = True,
) -> list[str]:
    proposal = payload.get("proposal") or payload
    updates = proposal.get("architecture_updates") or payload.get("architecture_updates") or []
    if not updates:
        raise ValueError("Patch has no architecture_updates.")

    messages: list[str] = []
    for update in updates:
        messages.append(apply_architecture_update(workspace, update, dry_run=dry_run))

    validation_cmd = proposal.get("validation_command") or payload.get("validation_command")
    if run_validation and validation_cmd and not dry_run:
        result = subprocess.run(
            validation_cmd,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Validation failed ({validation_cmd}):\n{result.stdout}\n{result.stderr}"
            )
        messages.append(f"Validation passed: {validation_cmd}")

    return messages


def load_patch(patch_id: str, patches_dir: Path) -> dict[str, Any]:
    path = patches_dir / f"{patch_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Patch not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    from healing.paths import QUEUE_PATCHES

    parser = argparse.ArgumentParser(description="Apply POM healing patch to pages/*.py")
    parser.add_argument("--patch-id", required=True)
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    payload = load_patch(args.patch_id, QUEUE_PATCHES)
    try:
        messages = apply_patch_payload(
            payload,
            workspace=workspace,
            dry_run=args.dry_run,
            run_validation=not args.no_validate,
        )
        for msg in messages:
            print(f"[ok] {msg}")
        return 0
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
