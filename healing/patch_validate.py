"""Hand-rolled validators for healing patch proposals (no jsonschema dep)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


REQUIRED_UPDATE_KEYS = ("file", "symbol", "before", "after")


def validate_proposal_structure(proposal: dict[str, Any]) -> list[str]:
    """Return human-readable errors; empty list means structure is complete."""
    errors: list[str] = []
    updates = proposal.get("architecture_updates")
    if not updates or not isinstance(updates, list):
        return ["architecture_updates must be a non-empty list"]

    for i, update in enumerate(updates):
        if not isinstance(update, dict):
            errors.append(f"architecture_updates[{i}] must be an object")
            continue
        for key in REQUIRED_UPDATE_KEYS:
            value = update.get(key)
            if value is None or str(value).strip() == "":
                errors.append(f"architecture_updates[{i}].{key} is required")
        after = str(update.get("after", ""))
        if "TODO" in after:
            errors.append(f"architecture_updates[{i}].after still contains TODO")
        before = str(update.get("before", ""))
        if (
            before.strip()
            and after.strip()
            and before.strip() == after.strip()
            and "TODO" not in after
        ):
            errors.append(
                f"architecture_updates[{i}].after must differ from before "
                "(no-op locator change)"
            )
    return errors


def validate_before_matches_source(
    workspace: Path,
    update: dict[str, Any],
) -> list[str]:
    """Ensure `before` (or current property return) still exists in the target file."""
    rel = str(update.get("file") or "").strip()
    if not rel:
        return ["update.file is required for source check"]
    file_path = workspace / rel
    if not file_path.is_file():
        return [f"page file not found: {rel}"]

    content = file_path.read_text(encoding="utf-8")
    before = str(update.get("before") or "")
    symbol = str(update.get("symbol") or "")

    if before and before in content:
        return []

    if symbol:
        from healing.locator_source import extract_property_return_expression

        try:
            current = extract_property_return_expression(
                content, symbol
            )
        except Exception:
            current = None
        if current is not None and before and before.strip() == current.strip():
            return []
        if current is not None and before and before in content:
            return []
        # Property exists but before does not match live source.
        if current is not None:
            return [
                f"before for '{symbol}' does not match live source in {rel} "
                f"(live={current!r})"
            ]
        return [f"could not find property '{symbol}' in {rel}"]

    if before:
        return [f"before expression not found in {rel}"]
    return ["before is empty and no symbol to resolve"]


def validate_proposal(
    proposal: dict[str, Any],
    *,
    workspace: Path | None = None,
    check_source: bool = False,
) -> list[str]:
    """Validate proposal structure and optionally that before matches live pages."""
    errors = validate_proposal_structure(proposal)
    if errors or not check_source:
        return errors
    if workspace is None:
        from healing.paths import get_workspace

        workspace = get_workspace()
    for i, update in enumerate(proposal.get("architecture_updates") or []):
        if not isinstance(update, dict):
            continue
        for err in validate_before_matches_source(workspace, update):
            errors.append(f"architecture_updates[{i}]: {err}")
    return errors


def is_proposal_complete(
    proposal: dict[str, Any],
    *,
    workspace: Path | None = None,
    check_source: bool = False,
) -> bool:
    return not validate_proposal(
        proposal, workspace=workspace, check_source=check_source
    )
