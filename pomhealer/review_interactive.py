"""Interactive terminal session for healing review."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, TextIO

from pomhealer.queue import list_patch_ready
from pomhealer.review import (
    decision_defer,
    decision_heal,
    decision_promote_all,
    decision_skip,
    write_summary,
)
from pomhealer.paths import FAILURES_DIR, QUEUE_PATCHES
from pomhealer.pom_apply import load_patch
from pomhealer.review_display import (
    SKIP_REASONS,
    format_menu,
    format_review_card,
    format_skip_menu,
)


def _read_line(prompt: str, input_fn: Callable[[str], str]) -> str:
    try:
        return input_fn(prompt).strip()
    except EOFError:
        return "q"


def _resolve_skip_reason(choice: str, input_fn: Callable[[str], str]) -> str:
    if choice == "c":
        custom = _read_line("Enter skip reason: ", input_fn)
        return custom or "User chose not to heal"
    try:
        index = int(choice) - 1
        if 0 <= index < len(SKIP_REASONS):
            return SKIP_REASONS[index]
    except ValueError:
        pass
    return "User chose not to heal"


def _confirm_high_risk(input_fn: Callable[[str], str]) -> bool:
    answer = _read_line("Type 'yes' to apply this high-risk patch: ", input_fn)
    return answer.lower() == "yes"


def run_interactive_review(
    workspace: Path,
    *,
    input_fn: Callable[[str], str] | None = None,
    output: TextIO | None = None,
    auto_confirm: bool = False,
) -> int:
    """Walk through patch_ready entries with a guided menu."""
    out = output or sys.stdout
    read = input_fn or input
    decision_promote_all()
    ready = list_patch_ready()
    if not ready:
        out.write("\n✓ No patches awaiting review.\n\n")
        return 0

    count = len(ready)
    out.write(f"\nStarting interactive review — {count} patch(es) pending.\n")

    quit_requested = False
    deferred_count = 0
    while True:
        if quit_requested:
            break
        ready = list_patch_ready()
        if not ready:
            break
        total = len(ready)
        entry = ready[0]
        patch_id = entry.get("patch_id")
        if not patch_id:
            continue

        while True:
            try:
                payload = load_patch(patch_id, QUEUE_PATCHES)
            except FileNotFoundError:
                break
            proposal = payload.get("proposal") or payload
            high_risk = (proposal.get("risk_level") or "").lower() == "high"

            out.write("\n")
            out.write(
                format_review_card(
                    patch_id,
                    payload,
                    workspace=workspace,
                    index=1,
                    total=total,
                )
            )
            out.write("\n")
            out.write(format_menu(high_risk=high_risk and not auto_confirm))
            choice = _read_line("Your choice [1-5 / q]: ", read).lower()

            if choice in ("1", "h", "heal"):
                if high_risk and not auto_confirm and not _confirm_high_risk(read):
                    out.write("Heal cancelled — high-risk confirmation not given.\n")
                    continue
                rc = decision_heal(patch_id, workspace=workspace, dry_run=False)
                if rc == 0:
                    out.write(f"\n✓ Healed {patch_id}\n")
                else:
                    out.write(f"\n✗ Could not heal {patch_id}\n")
                break

            if choice in ("2", "s", "skip"):
                out.write("\n")
                out.write(format_skip_menu())
                skip_choice = _read_line("Skip reason choice: ", read)
                reason = _resolve_skip_reason(skip_choice, read)
                decision_skip(patch_id, reason)
                out.write(f"\n○ Skipped {patch_id} — {reason}\n")
                break

            if choice in ("3", "d", "defer"):
                decision_defer(patch_id)
                deferred_count += 1
                out.write(f"\n… Deferred {patch_id} (status → deferred)\n")
                break

            if choice in ("4", "f", "failure"):
                failure_id = proposal.get("failure_id", "")
                failure_md = FAILURES_DIR / f"{failure_id}.md"
                if failure_md.exists():
                    out.write("\n")
                    out.write(failure_md.read_text(encoding="utf-8"))
                    out.write("\n")
                else:
                    out.write(f"\nFailure report not found: {failure_md}\n")
                try:
                    from pomhealer.queue import load_failure_payload

                    failure = load_failure_payload(failure_id)
                    shot = (failure.get("artifacts") or {}).get("screenshot")
                    if shot:
                        out.write(f"\nScreenshot: {Path(shot).resolve()}\n")
                except (FileNotFoundError, OSError):
                    pass
                continue

            if choice in ("5", "dry", "dry-run", "dryrun"):
                rc = decision_heal(patch_id, workspace=workspace, dry_run=True)
                if rc == 0:
                    out.write("\n✓ Dry run succeeded — no files written.\n")
                else:
                    out.write("\n✗ Dry run failed.\n")
                continue

            if choice in ("q", "quit", "exit"):
                out.write("\nReview session ended. Remaining patches stay patch_ready.\n")
                quit_requested = True
                break

            out.write("Invalid choice. Enter 1-5, or q to quit.\n")

    remaining = list_patch_ready()
    if not remaining:
        from pomhealer.queue import list_deferred

        deferred_left = list_deferred()
        if deferred_left or deferred_count:
            out.write(
                f"\nNo patch_ready items left "
                f"({len(deferred_left)} deferred — re-queue with "
                "`python -m pomhealer.review --promote P-<id>` or `--list-deferred`).\n"
            )
        else:
            out.write("\nAll patches processed.\n")
        write_summary(workspace)
    else:
        pending = len(remaining)
        out.write(f"\n{pending} patch(es) still awaiting review")
        if deferred_count:
            out.write(f" ({deferred_count} deferred this session)")
        out.write(".\n")
        out.write("Resume anytime: python -m pomhealer.review --interactive\n")
    out.write("\n")
    return 0
