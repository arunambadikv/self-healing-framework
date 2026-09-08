"""Human-in-the-loop review and apply/skip for pomhealer-queue patches."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pomhealer.queue import (
    get_index_summary,
    list_deferred,
    list_patch_ready,
    load_failure_payload,
    move_patch_file,
    update_patch_status,
)
from pomhealer.paths import QUEUE_APPLIED, QUEUE_PATCHES, QUEUE_SKIPPED, QUEUE_SUMMARIES, ensure_queue_dirs
from pomhealer.pom_apply import apply_patch_payload, load_patch
from pomhealer.review_display import format_patch_list, format_review_card


def format_patch_for_human(patch_id: str, payload: dict[str, Any], workspace: Path) -> str:
    """Format a patch for display (CLI --show and agent review cards)."""
    return format_review_card(patch_id, payload, workspace=workspace)


def write_skip_rca(patch_id: str, payload: dict[str, Any], reason: str) -> Path:
    proposal = payload.get("proposal") or payload
    failure_id = proposal.get("failure_id", "")
    lines = [
        f"# Skipped patch {patch_id}",
        "",
        f"**Reason:** {reason}",
        f"**Failure:** {failure_id}",
        "",
        "## Suggested RCA / bug report",
        "",
        "- Verify whether the application UI changed vs test expectation.",
        "- Check environment URL and test data.",
        "- If locator is correct, file a product bug with failure artifact:",
        f"  - `pomhealer-artifacts/failures/{failure_id}.md`",
        "",
        "## Classification hints",
        "",
        "- **selector_break** — update page object after product change",
        "- **app_regression** — product defect; do not heal test",
        "- **test_data** — fix data/fixtures",
        "- **flake** — stabilize wait or retry policy (do not weaken assertions)",
    ]
    if failure_id:
        try:
            failure = load_failure_payload(failure_id)
            lines.extend(["", "## Error excerpt", "", f"```\n{failure['error']['message'][:800]}\n```"])
        except FileNotFoundError:
            pass
    path = QUEUE_SKIPPED / f"{patch_id}-rca.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def decision_heal(patch_id: str, *, workspace: Path, dry_run: bool = False) -> int:
    payload = load_patch(patch_id, QUEUE_PATCHES)
    proposal = payload.get("proposal") or payload
    from pomhealer.patch_validate import validate_proposal

    errors = validate_proposal(proposal, workspace=workspace, check_source=True)
    if proposal.get("proposal_status") == "awaiting_agent" or errors:
        detail = "; ".join(errors) if errors else "still awaiting_agent"
        print(
            f"[error] Patch not ready to apply ({detail}). Complete MCP repair, then run:\n"
            f"  python -m pomhealer.review --promote {patch_id}"
        )
        return 1
    apply_patch_payload(payload, workspace=workspace, dry_run=dry_run)
    if not dry_run:
        update_patch_status(patch_id, "applied")
        move_patch_file(patch_id, QUEUE_APPLIED)
        from pomhealer.reports import emit_patch_applied

        emit_patch_applied(patch_id, proposal)
    print(f"[ok] Applied patch {patch_id}")
    return 0


def decision_skip(patch_id: str, reason: str) -> int:
    payload = load_patch(patch_id, QUEUE_PATCHES)
    write_skip_rca(patch_id, payload, reason)
    update_patch_status(patch_id, "skipped", notes=reason)
    move_patch_file(patch_id, QUEUE_SKIPPED)
    from pomhealer.reports import emit_patch_skipped

    emit_patch_skipped(patch_id, payload.get("proposal") or payload, reason)
    print(f"[ok] Skipped patch {patch_id}; RCA written")
    return 0


def decision_defer(patch_id: str) -> int:
    """Mark patch deferred so it leaves the patch_ready review queue."""
    update_patch_status(patch_id, "deferred", notes="Deferred by reviewer")
    print(f"[ok] Deferred patch {patch_id} (status → deferred; re-queue with --promote later if needed)")
    return 0


def decision_promote(patch_id: str) -> int:
    from pomhealer.patch_promote import promote_patch

    try:
        promote_patch(patch_id)
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        return 1
    except ValueError as exc:
        print(f"[error] {exc}")
        return 1
    except KeyError as exc:
        print(f"[error] Unknown patch_id: {patch_id} ({exc})")
        return 1
    print(f"[ok] Promoted patch {patch_id} → patch_ready")
    return 0


def decision_promote_all() -> int:
    from pomhealer.patch_promote import promote_all_complete

    promoted = promote_all_complete()
    if not promoted:
        print("No complete patches to promote (awaiting_agent with TODO cleared).")
        return 0
    for patch_id in promoted:
        print(f"[ok] Promoted patch {patch_id} → patch_ready")
    return 0


def write_summary(workspace: Path) -> Path:
    from pomhealer.artifact_naming import utc_stamp

    ensure_queue_dirs()
    counts = get_index_summary()
    ts = utc_stamp()
    path = QUEUE_SUMMARIES / f"summary-{ts}.md"
    ready = list_patch_ready()
    deferred = list_deferred()
    lines = [
        "# Healing session summary",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Counts",
        "",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- **{status}:** {count}")
    lines.append("")
    if ready:
        lines.extend(["## Still awaiting review", ""] + [f"- {e.get('patch_id')}" for e in ready])
    else:
        lines.append("No `patch_ready` items awaiting review.")
    if deferred:
        lines.extend(
            [
                "",
                "## Deferred (re-queue with `--promote P-<id>`)",
                "",
            ]
            + [f"- {e.get('patch_id')}" for e in deferred]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and apply pomhealer-queue patches.")
    parser.add_argument("--list", action="store_true", help="List patch_ready entries (table view).")
    parser.add_argument(
        "--list-deferred",
        action="store_true",
        help="List deferred patches (re-queue later with --promote P-<id>).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON for --list / --list-deferred / --show.",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Guided review session with heal/skip/defer menu (default when run with no flags on a TTY).",
    )
    parser.add_argument("--show", metavar="PATCH_ID", help="Show detailed review card for one patch.")
    parser.add_argument("--patch", metavar="PATCH_ID")
    parser.add_argument("--promote", metavar="PATCH_ID", help="Promote complete patch to patch_ready.")
    parser.add_argument("--promote-all", action="store_true", help="Promote all complete awaiting_agent patches.")
    parser.add_argument("--decision", choices=("heal", "skip", "defer"))
    parser.add_argument("--reason", default="User chose not to heal")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip high-risk confirmation prompts (decision already confirmed in chat/UI).",
    )
    parser.add_argument("--workspace", default=".", type=Path)
    args = parser.parse_args()
    from pomhealer.paths import configure_workspace

    workspace = configure_workspace(args.workspace.resolve())
    from pomhealer.doctor import load_dotenv_files

    load_dotenv_files(workspace)
    ensure_queue_dirs()
    from pomhealer.package_sync import refresh_packaged_assets_if_stale

    refresh_packaged_assets_if_stale(workspace)
    from pomhealer.artifact_import import import_ci_artifacts

    imported = import_ci_artifacts(workspace)
    if imported.imported:
        print(imported.summary_line())
    from pomhealer.queue import archive_terminal_patch_files

    archive_terminal_patch_files()

    no_action = not any(
        [
            args.list,
            args.list_deferred,
            args.interactive,
            args.show,
            args.patch,
            args.promote,
            args.promote_all,
            args.summary,
        ]
    )
    if no_action and sys.stdin.isatty():
        from pomhealer.review_interactive import run_interactive_review

        return run_interactive_review(workspace, auto_confirm=args.yes)

    if args.interactive:
        from pomhealer.review_interactive import run_interactive_review

        return run_interactive_review(workspace, auto_confirm=args.yes)

    if args.list:
        ready = list_patch_ready()
        if args.json:
            print(json.dumps({"status": "patch_ready", "entries": ready}, indent=2, ensure_ascii=True))
        else:
            print(format_patch_list(ready, workspace=workspace))
        return 0

    if args.list_deferred:
        deferred = list_deferred()
        if args.json:
            print(json.dumps({"status": "deferred", "entries": deferred}, indent=2, ensure_ascii=True))
            return 0
        if not deferred:
            print("No deferred patches.")
            return 0
        print(format_patch_list(deferred, workspace=workspace))
        print("\nRe-queue a deferred patch: python -m pomhealer.review --promote P-<id>")
        return 0

    if args.promote:
        return decision_promote(args.promote)

    if args.promote_all:
        return decision_promote_all()

    if args.show:
        payload = load_patch(args.show, QUEUE_PATCHES)
        if args.json:
            print(json.dumps({"patch_id": args.show, "payload": payload}, indent=2, ensure_ascii=True))
        else:
            print(format_patch_for_human(args.show, payload, workspace))
        return 0

    if args.patch and args.decision:
        if args.decision == "heal":
            if not args.yes and not args.dry_run:
                payload = load_patch(args.patch, QUEUE_PATCHES)
                proposal = payload.get("proposal") or payload
                if (proposal.get("risk_level") or "").lower() == "high":
                    print(
                        "[error] High-risk patch requires confirmation. "
                        "Re-run with --yes after the user confirms in chat."
                    )
                    return 1
            return decision_heal(args.patch, workspace=workspace, dry_run=args.dry_run)
        if args.decision == "skip":
            return decision_skip(args.patch, args.reason)
        return decision_defer(args.patch)

    if args.summary:
        write_summary(workspace)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
