"""Human-friendly formatting for healing review sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from healing.healing_queue import load_failure_payload
from healing.pom_apply import load_patch
from healing.paths import QUEUE_PATCHES

RISK_ICONS = {"low": "●", "medium": "◐", "high": "▲", "unknown": "?"}
SKIP_REASONS = (
    "Suspected app regression — locator is correct, product is broken",
    "Proposal looks wrong — needs re-propose via MCP",
    "Flaky failure — not a locator issue",
    "Out of scope for this session",
)


def _short_test_name(nodeid: str) -> str:
    if "::" in nodeid:
        return nodeid.split("::", 1)[1]
    return nodeid


def _relative_file(path: str, workspace: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(workspace.resolve()))
    except ValueError:
        return path


def _risk_label(level: str) -> str:
    level = (level or "unknown").lower()
    icon = RISK_ICONS.get(level, RISK_ICONS["unknown"])
    return f"{icon} {level.upper()}"


def _failure_context(failure_id: str) -> dict[str, Any]:
    try:
        failure = load_failure_payload(failure_id)
    except FileNotFoundError:
        return {}
    env = failure.get("environment") or {}
    failing = failure.get("failing_step") or {}
    artifacts = failure.get("artifacts") or {}
    screenshot = artifacts.get("screenshot") or ""
    return {
        "failure": failure,
        "test_nodeid": failure.get("test", {}).get("nodeid", ""),
        "test_short": _short_test_name(failure.get("test", {}).get("nodeid", "")),
        "error_type": failure.get("error", {}).get("type", ""),
        "error_message": (failure.get("error", {}).get("message") or "")[:400],
        "architecture_ref": failure.get("architecture_ref", ""),
        "page_url": env.get("page_url") or env.get("base_url", ""),
        "failing_page": failing.get("page_class", ""),
        "failing_method": failing.get("method", ""),
        "failing_action": failing.get("action", ""),
        "locator_id": failing.get("locator_id", ""),
        "screenshot": screenshot,
    }


def format_patch_list(entries: list[dict[str, Any]], *, workspace: Path) -> str:
    if not entries:
        return "No patches awaiting review."

    lines = [
        f"Patches awaiting review ({len(entries)}):",
        "",
        f"  {'#':<3} {'Patch ID':<16} {'Failure':<16} {'Risk':<8} Test",
        f"  {'-' * 3} {'-' * 16} {'-' * 16} {'-' * 8} {'-' * 24}",
    ]
    for index, entry in enumerate(entries, start=1):
        patch_id = entry.get("patch_id", "?")
        failure_id = entry.get("failure_id", "?")
        risk = "?"
        test_short = "?"
        try:
            payload = load_patch(patch_id, QUEUE_PATCHES)
            proposal = payload.get("proposal") or payload
            risk = (proposal.get("risk_level") or "?").lower()
            ctx = _failure_context(proposal.get("failure_id", ""))
            test_short = ctx.get("test_short") or "?"
        except FileNotFoundError:
            pass
        lines.append(f"  {index:<3} {patch_id:<16} {failure_id:<16} {risk:<8} {test_short}")

    lines.extend(
        [
            "",
            "Start interactive review:",
            "  python -m healing.healing_review --interactive",
            "",
            "Or inspect one patch:",
            "  python -m healing.healing_review --show P-<id>",
        ]
    )
    return "\n".join(lines)


def format_review_card(
    patch_id: str,
    payload: dict[str, Any],
    *,
    workspace: Path,
    index: int | None = None,
    total: int | None = None,
) -> str:
    proposal = payload.get("proposal") or payload
    failure_id = proposal.get("failure_id", "")
    ctx = _failure_context(failure_id)
    risk = _risk_label(proposal.get("risk_level", "unknown"))

    header = f"Patch {patch_id}"
    if index is not None and total is not None:
        header = f"Patch {index} of {total} — {patch_id}"

    width = 62
    lines = [
        "═" * width,
        f"  Healing Review — {header}",
        f"  Failure: {failure_id}" if failure_id else "",
        "═" * width,
        "",
    ]

    if ctx:
        lines.extend(
            [
                "TEST",
                f"  {ctx.get('test_nodeid', 'unknown')}",
                "",
                "WHAT FAILED",
            ]
        )
        if ctx.get("architecture_ref"):
            lines.append(f"  Ref: {ctx['architecture_ref']}")
        if ctx.get("failing_page") and ctx.get("failing_method"):
            lines.append(
                f"  Step: {ctx['failing_page']}.{ctx['failing_method']} ({ctx.get('failing_action', '')})"
            )
        if ctx.get("page_url"):
            lines.append(f"  URL: {ctx['page_url']}")
        if ctx.get("error_type"):
            lines.append(f"  Error: {ctx['error_type']}")
            if ctx.get("error_message"):
                lines.append(f"  {ctx['error_message'][:200]}")
        if ctx.get("screenshot"):
            shot = ctx["screenshot"]
            try:
                shot_display = str(Path(shot).resolve())
            except OSError:
                shot_display = shot
            lines.append(f"  Screenshot: {shot_display}")
        lines.append("")

    updates = proposal.get("architecture_updates") or []
    if updates:
        lines.extend([f"PROPOSED FIX  [risk: {risk}]", ""])
        for upd in updates:
            file_ref = _relative_file(upd.get("file", ""), workspace)
            lines.extend(
                [
                    f"  File:   {file_ref}",
                    f"  Symbol: {upd.get('symbol', '?')}",
                    "",
                    "  Before:",
                    f"    {upd.get('before', '')}",
                    "  After:",
                    f"    {upd.get('after', '')}",
                    "",
                ]
            )

    validation = proposal.get("validation_command", "")
    if validation:
        lines.extend(["VALIDATION (runs on heal)", f"  {validation}", ""])

    lines.append("─" * width)
    return "\n".join(line for line in lines if line is not None)


def format_menu(*, high_risk: bool = False) -> str:
    lines = [
        "  [1] Heal     — apply patch and run validation",
        "  [2] Skip     — reject with reason (writes RCA)",
        "  [3] Defer    — decide later (status → deferred)",
        "  [4] Failure  — show full failure report",
        "  [5] Dry run  — preview apply without writing files",
        "  [q] Quit     — exit review session",
        "",
    ]
    if high_risk:
        lines.insert(
            0,
            "  ⚠ HIGH RISK patch — heal requires typing 'yes' to confirm.\n",
        )
    return "\n".join(lines)


def format_skip_menu() -> str:
    lines = ["Skip reason:", ""]
    for index, reason in enumerate(SKIP_REASONS, start=1):
        lines.append(f"  [{index}] {reason}")
    lines.extend(["  [c] Custom reason", ""])
    return "\n".join(lines)
