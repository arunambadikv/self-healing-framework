"""Post-pytest healing chain (architecture scan, propose, MCP runner)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from healing.paths import MANIFEST_JSON


def _load_healing_config(workspace: Path) -> dict[str, Any]:
    from healing.gates_config import load_healing_yaml

    return load_healing_yaml(workspace)


def is_auto_enabled(workspace: Path | None = None) -> bool:
    workspace = (workspace or Path.cwd()).resolve()
    from healing.doctor import load_dotenv_files

    load_dotenv_files(workspace)
    if os.environ.get("HEALING_MCP_AUTO", "").strip() in ("1", "true", "yes"):
        return True
    config = _load_healing_config(workspace)
    return bool(config.get("healing_mcp", {}).get("auto_after_test", False))


def manifest_is_stale(workspace: Path) -> bool:
    from healing.architecture_scan import build_manifest

    manifest_path = workspace / MANIFEST_JSON
    if not manifest_path.exists():
        return True
    try:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        current = build_manifest(workspace)
        return old.get("content_hash") != current.get("content_hash")
    except Exception:
        return True


def run_architecture_scan_if_needed(workspace: Path) -> int:
    if not manifest_is_stale(workspace):
        return 0
    from healing.architecture_scan import build_manifest, write_manifest

    manifest = build_manifest(workspace)
    write_manifest(manifest, workspace)
    return 0


def run_pom_propose_all(workspace: Path) -> int:
    """Create stubs only for healable failures captured in this pytest session."""
    from healing.healing_queue import list_unprocessed_failures
    from healing.pom_propose import process_failure_entry
    from healing.session_state import session_had_healable_failures, session_healable_failure_ids

    if not session_had_healable_failures():
        print("[healing] pom_propose: no session healable failures to process")
        return 0

    session_ids = session_healable_failure_ids()
    pending = list_unprocessed_failures()
    if session_ids:
        pending = [e for e in pending if e.get("failure_id") in session_ids]
    # else: anon-only notes (unit tests) → process all pending

    if not pending:
        print("[healing] pom_propose: no pending failures from this session")
        return 0

    rc = 0
    for entry in pending:
        try:
            process_failure_entry(entry, workspace=workspace)
        except Exception as exc:
            print(f"[healing] pom_propose failed for {entry.get('failure_id')}: {exc}")
            rc = 1
    return rc


def run_mcp_propose_all(workspace: Path) -> int:
    """Complete the latest session patch(es) via MCP (newest first; one per architecture_ref)."""
    from healing.doctor import load_dotenv_files
    from healing.healing_queue import select_latest_awaiting_patches
    from healing.llm_config import resolve_llm_config
    from healing.mcp_propose_runner import process_patch_entry
    from healing.session_state import session_new_patch_ids

    load_dotenv_files(workspace)
    config = resolve_llm_config()
    session_patches = session_new_patch_ids()
    if not session_patches:
        print(
            "[healing] mcp_propose_runner: no session patches to process "
            "(stale awaiting_agent skipped; "
            "run python -m healing.mcp_propose_runner --patch-id P-... manually)"
        )
        return 0

    session_entries = [
        e for e in select_latest_awaiting_patches() if e.get("patch_id") in session_patches
    ]
    # Prefer absolute newest session patch when multiple refs; still run all latest-per-ref
    # that were created this session (already newest-first from select_latest).
    if not session_entries:
        # Session created a patch that is not awaiting (unlikely) — try raw session ids latest
        from healing.healing_queue import list_awaiting_agent, sort_entries_newest_first

        session_entries = sort_entries_newest_first(
            [e for e in list_awaiting_agent() if e.get("patch_id") in session_patches]
        )

    if not session_entries:
        print(
            "[healing] mcp_propose_runner: session patches are not awaiting_agent "
            "(already patch_ready or missing) — nothing to run"
        )
        return 0

    latest = session_entries[0]
    print(
        f"[healing] mcp_propose_runner: processing latest patch "
        f"{latest.get('patch_id')} first ({len(session_entries)} session patch(es); "
        f"provider={config.provider})"
    )

    rc = 0
    for entry in session_entries:
        patch_id = entry.get("patch_id")
        try:
            if not process_patch_entry(entry, workspace=workspace, config=config):
                rc = 1
        except Exception as exc:
            print(f"[healing] mcp_propose_runner failed for {patch_id}: {exc}")
            rc = 1
    return rc


def should_run_post_test_chain(workspace: Path | None = None) -> bool:
    """True when auto is enabled and this session captured healable locator failures."""
    workspace = (workspace or Path.cwd()).resolve()
    if not is_auto_enabled(workspace):
        return False
    from healing.session_state import session_had_healable_failures

    return session_had_healable_failures()


def run_post_test_chain(workspace: Path | None = None) -> int:
    """Run optional post-test healing steps when HEALING_MCP_AUTO=1 or config flag set.

    Returns 0 on success / skip, non-zero when a chain step failed.
    """
    workspace = (workspace or Path.cwd()).resolve()
    if not is_auto_enabled(workspace):
        return 0
    if not should_run_post_test_chain(workspace):
        print(
            "\n[healing] HEALING_MCP_AUTO enabled — skipping post-test chain "
            "(no healable locator failures captured this session)"
        )
        return 0
    print("\n[healing] HEALING_MCP_AUTO enabled — running post-test chain (this session only)")
    steps = (
        ("architecture_scan", run_architecture_scan_if_needed),
        ("pom_propose", run_pom_propose_all),
        ("mcp_propose_runner", run_mcp_propose_all),
    )
    failed: list[str] = []
    for name, runner in steps:
        rc = runner(workspace)
        if rc != 0:
            failed.append(name)
    if failed:
        print(f"[healing] post-test chain completed with errors: {', '.join(failed)}")
        return 1
    return 0
