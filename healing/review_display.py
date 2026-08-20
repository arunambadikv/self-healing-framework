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

# Fixed section labels — interactive + --show always use this order.
CARD_LABELS = (
    "Patch summary",
    "Patch name",
    "Why failure happened",
    "Error",
    "Screenshot",
    "Before",
    "After",
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
        "classification": failure.get("classification", ""),
    }


def _first_update(proposal: dict[str, Any]) -> dict[str, Any]:
    updates = proposal.get("architecture_updates") or []
    return updates[0] if updates and isinstance(updates[0], dict) else {}


def _one_sentence_summary(proposal: dict[str, Any], ctx: dict[str, Any]) -> str:
    reason = (proposal.get("risk_reason") or "").strip()
    if reason:
        # Keep to one sentence / ~160 chars for the card.
        first = reason.split(". ")[0].strip().rstrip(".")
        if first:
            return first + "."
    upd = _first_update(proposal)
    symbol = upd.get("symbol") or ctx.get("locator_id") or "locator"
    test = ctx.get("test_short") or "test"
    return f"Replace broken {symbol} locator so {test} can proceed."


def _why_failure_happened(proposal: dict[str, Any], ctx: dict[str, Any]) -> str:
    parts: list[str] = []
    classification = (
        proposal.get("classification")
        or ctx.get("classification")
        or ""
    ).strip()
    if classification:
        parts.append(classification)
    ref = ctx.get("architecture_ref") or ""
    if ctx.get("failing_page") and ctx.get("failing_method"):
        step = (
            f"{ctx['failing_page']}.{ctx['failing_method']}"
            f" ({ctx.get('failing_action') or 'action'})"
        )
        parts.append(f"failed at {step}")
    elif ref:
        parts.append(f"failed on {ref}")
    if ctx.get("error_type"):
        parts.append(ctx["error_type"])
    msg = (ctx.get("error_message") or "").strip()
    if msg:
        # Prefer the first call-log / timeout line for clarity.
        first_line = msg.splitlines()[0].strip()
        if first_line and first_line not in parts:
            parts.append(first_line)
    return " — ".join(parts) if parts else "(failure context unavailable)"


def _patch_error_block(
    proposal: dict[str, Any],
    *,
    workspace: Path,
) -> str:
    """Validation / completeness problems with the proposal, if any."""
    from healing.patch_validate import validate_proposal

    errors = validate_proposal(proposal, workspace=workspace, check_source=True)
    if errors:
        return "; ".join(errors)
    after = str(_first_update(proposal).get("after") or "")
    if "TODO" in after:
        return "architecture_updates[].after still contains TODO"
    return "None"


def _screenshot_display(ctx: dict[str, Any]) -> str:
    shot = ctx.get("screenshot") or ""
    if not shot:
        return "(none)"
    try:
        return str(Path(shot).resolve())
    except OSError:
        return str(shot)


def _section(label: str, body: str) -> list[str]:
    text = (body or "").strip() or "(none)"
    lines = [label]
    for part in text.splitlines() or ["(none)"]:
        lines.append(f"  {part}" if part.strip() else "")
    lines.append("")
    return lines


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
    """Always the same fixed layout for interactive review and --show."""
    proposal = payload.get("proposal") or payload
    failure_id = proposal.get("failure_id", "")
    ctx = _failure_context(failure_id)
    upd = _first_update(proposal)
    risk = _risk_label(proposal.get("risk_level", "unknown"))

    progress = ""
    if index is not None and total is not None:
        progress = f" ({index} of {total})"

    width = 62
    lines: list[str] = [
        "═" * width,
        f"  Healing Review{progress}  [risk: {risk}]",
        "═" * width,
        "",
    ]

    lines.extend(_section("Patch summary", _one_sentence_summary(proposal, ctx)))
    lines.extend(_section("Patch name", patch_id))
    lines.extend(_section("Why failure happened", _why_failure_happened(proposal, ctx)))
    lines.extend(
        _section("Error", _patch_error_block(proposal, workspace=workspace))
    )
    lines.extend(_section("Screenshot", _screenshot_display(ctx)))

    before = str(upd.get("before") or "").strip() or "(none)"
    after = str(upd.get("after") or "").strip() or "(none)"
    file_ref = _relative_file(str(upd.get("file") or ""), workspace) if upd.get("file") else ""
    symbol = str(upd.get("symbol") or "").strip()
    locator_meta = " · ".join(p for p in (file_ref, symbol) if p)

    before_body = before
    if locator_meta:
        before_body = f"{before}\n({locator_meta})"
    lines.extend(_section("Before", before_body))
    lines.extend(_section("After", after))

    validation = (proposal.get("validation_command") or "").strip()
    if validation:
        lines.extend(_section("Validation (runs on heal)", validation))

    lines.append("─" * width)
    return "\n".join(lines)


def format_menu(*, high_risk: bool = False) -> str:
    lines = [
        "Select an option, then press Enter to continue:",
        "",
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
