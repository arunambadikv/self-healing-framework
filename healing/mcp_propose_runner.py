"""Run Cursor SDK + Playwright MCP to complete healing patch proposals."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from healing.healing_queue import (
    is_patch_complete,
    list_awaiting_agent,
    load_failure_payload,
    select_latest_awaiting_patches,
)
from healing.paths import QUEUE_PATCHES, ensure_queue_dirs
from healing.skill_paths import load_skill_text


def resolve_storage_state_path(failure: dict[str, Any], workspace: Path) -> Path | None:
    """Return absolute path to failure storage_state if it exists on disk."""
    raw = (failure.get("artifacts") or {}).get("storage_state")
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = workspace / path
    return path if path.exists() else None


def _with_storage_state_args(args: list[str], storage_state: Path) -> list[str]:
    cleaned = [a for a in args if a != "--isolated" and not str(a).startswith("--storage-state")]
    cleaned.append("--isolated")
    cleaned.append(f"--storage-state={storage_state.resolve()}")
    return cleaned


def _load_mcp_servers(
    workspace: Path,
    *,
    storage_state: Path | None = None,
) -> dict[str, Any]:
    """Load Playwright MCP stdio config from .cursor/mcp.json."""
    from cursor_sdk import StdioMcpServerConfig

    mcp_path = workspace / ".cursor" / "mcp.json"
    command = "npx"
    from healing.mcp_constants import PLAYWRIGHT_MCP_PACKAGE

    args: list[str] = [PLAYWRIGHT_MCP_PACKAGE]
    env: dict[str, str] = {}

    if mcp_path.exists():
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") or {}
        playwright = servers.get("playwright") or servers.get(
            "project-0-playwright-healing-framework-playwright"
        )
        if playwright and playwright.get("command"):
            command = playwright["command"]
            args = list(playwright.get("args") or [])
            env = dict(playwright.get("env") or {})

    if storage_state is not None:
        args = _with_storage_state_args(args, storage_state)
        env = {
            **env,
            "PLAYWRIGHT_MCP_STORAGE_STATE": str(storage_state.resolve()),
        }

    return {
        "playwright": StdioMcpServerConfig(
            command=command,
            args=args,
            env=env,
        )
    }


def _workspace_relative(path: Path, workspace: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path)


def build_agent_prompt(
    entry: dict[str, Any],
    workspace: Path,
    *,
    storage_state: Path | None = None,
) -> str:
    patch_id = entry.get("patch_id", "")
    task_path = QUEUE_PATCHES / f"{patch_id}-agent-task.md"
    if task_path.exists():
        task_text = task_path.read_text(encoding="utf-8")
    else:
        task_text = f"Complete patch {patch_id} for failure {entry.get('failure_id')}."

    skill_text = load_skill_text("playwright-locator-repair")
    patch_json = QUEUE_PATCHES / f"{patch_id}.json"
    patch_rel = _workspace_relative(patch_json, workspace)

    restore_note = ""
    if storage_state is not None:
        restore_note = (
            f"\nPlaywright MCP was started with `--isolated --storage-state={storage_state}`.\n"
            "Navigate to the failure `page_url` first, then snapshot.\n"
            "If needed, call `browser_set_storage_state` with that same path.\n"
        )
    else:
        restore_note = (
            "\nNo storage_state available — replay successful `test_steps` before the failing "
            "step (correct locators from pages/*.py), or navigate to `page_url` if sufficient.\n"
        )

    return f"""{skill_text}

---

# Automated MCP propose task

{task_text}
{restore_note}
## Instructions

1. Use Playwright MCP to reach the failure UI, then `browser_snapshot` to verify the correct locator.
2. Update `{patch_rel}` — replace TODO in `architecture_updates[].after`.
3. Update matching `{patch_id}.md` with human-readable summary.
4. Set `proposal_status` to `"complete"` (remove `"awaiting_agent"`).
5. Set accurate `risk_level`, `risk_reason`, and `validation_command`.
6. Do NOT apply changes to `pages/*.py` — human review applies patches later.

Return a one-line summary when done.
"""


def run_sdk_propose(
    prompt: str,
    *,
    workspace: Path,
    api_key: str,
    storage_state: Path | None = None,
) -> str:
    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

    from healing.mcp_constants import DEFAULT_MCP_MODEL

    model = os.environ.get("HEALING_MCP_MODEL", "").strip() or DEFAULT_MCP_MODEL
    mcp_servers = _load_mcp_servers(workspace, storage_state=storage_state)
    # Agent.prompt is synchronous; incomplete patches fail closed after return
    # (see is_patch_complete with check_source). No separate SDK timeout API is wired.
    result = Agent.prompt(
        prompt,
        AgentOptions(
            api_key=api_key,
            model=model,
            local=LocalAgentOptions(cwd=str(workspace)),
            mcp_servers=mcp_servers,
        ),
    )
    if result.status == "error":
        raise RuntimeError(f"SDK agent run failed: {result.result}")
    return str(result.result or "")


def process_patch_entry(entry: dict[str, Any], *, workspace: Path, api_key: str | None) -> bool:
    patch_id = entry.get("patch_id")
    if not patch_id:
        print(f"[skip] {entry.get('failure_id')}: no patch_id")
        return False

    patch_path = QUEUE_PATCHES / f"{patch_id}.json"
    if not patch_path.exists():
        print(f"[error] Patch file missing: {patch_path}")
        return False

    payload = json.loads(patch_path.read_text(encoding="utf-8"))
    proposal = payload.get("proposal") or payload
    if is_patch_complete(proposal, workspace=workspace, check_source=True):
        from healing.patch_promote import promote_patch

        promote_patch(patch_id)
        print(f"[ok] {patch_id} already complete → patch_ready")
        return True

    if not api_key:
        print(
            f"[error] {patch_id}: CURSOR_API_KEY required for MCP propose runner.\n"
            "  Capture/scan/stub/review/apply work without it.\n"
            "  Install SDK: pip install 'healing[mcp]'\n"
            "  Set key:      export CURSOR_API_KEY=cursor_...  (or put it in .env)\n"
            "  Check:        healing-doctor"
        )
        return False

    storage_state: Path | None = None
    failure_id = entry.get("failure_id") or proposal.get("failure_id")
    if failure_id:
        try:
            failure = load_failure_payload(str(failure_id))
            storage_state = resolve_storage_state_path(failure, workspace)
        except FileNotFoundError:
            storage_state = None

    if storage_state is not None:
        print(f"[healing] Using storage_state for {patch_id}: {storage_state}")
    else:
        print(f"[healing] No storage_state for {patch_id} — agent will use page_url / step replay")

    prompt = build_agent_prompt(entry, workspace, storage_state=storage_state)
    print(f"[healing] Running SDK + Playwright MCP for {patch_id}...")
    try:
        summary = run_sdk_propose(
            prompt,
            workspace=workspace,
            api_key=api_key,
            storage_state=storage_state,
        )
        print(f"[healing] Agent: {summary[:200]}")
    except Exception as exc:
        print(f"[error] SDK propose failed for {patch_id}: {exc}")
        return False

    payload = json.loads(patch_path.read_text(encoding="utf-8"))
    proposal = payload.get("proposal") or payload
    if not is_patch_complete(proposal, workspace=workspace, check_source=True):
        from healing.patch_validate import validate_proposal

        errs = validate_proposal(proposal, workspace=workspace, check_source=True)
        print(
            f"[error] {patch_id} still incomplete after agent run: "
            + ("; ".join(errs) if errs else "TODO remains")
        )
        return False

    from healing.patch_promote import promote_patch

    promote_patch(patch_id)
    print(f"[ok] {patch_id} → patch_ready")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete healing patches via Cursor SDK + Playwright MCP.")
    parser.add_argument("--list", action="store_true", help="List patches awaiting agent.")
    parser.add_argument("--process-all", action="store_true", help="Process all awaiting_agent patches.")
    parser.add_argument("--patch-id", help="Process single patch id.")
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit JSON for --list.")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    ensure_queue_dirs()

    from healing.doctor import load_dotenv_files

    load_dotenv_files(workspace)

    if args.list:
        awaiting = list_awaiting_agent()
        if args.json:
            print(json.dumps({"status": "awaiting_agent", "entries": awaiting}, indent=2, ensure_ascii=True))
            return 0
        if not awaiting:
            print("No patches awaiting agent.")
            return 0
        for entry in awaiting:
            print(f"- {entry.get('patch_id')} (failure {entry.get('failure_id')})")
        return 0

    api_key = os.environ.get("CURSOR_API_KEY", "").strip() or None

    if args.patch_id:
        entry = next(
            (e for e in list_awaiting_agent() if e.get("patch_id") == args.patch_id),
            None,
        )
        if entry is None:
            print(f"Patch not awaiting agent: {args.patch_id}")
            return 1
        return 0 if process_patch_entry(entry, workspace=workspace, api_key=api_key) else 1

    if args.process_all:
        awaiting = select_latest_awaiting_patches()
        all_awaiting = list_awaiting_agent()
        skipped = len(all_awaiting) - len(awaiting)
        if not awaiting:
            print("No patches awaiting agent.")
            return 0
        if skipped:
            print(
                f"[healing] Processing {len(awaiting)} latest patch(es) "
                f"(skipped {skipped} older duplicate architecture_ref)"
            )
        else:
            print(f"[healing] Processing {len(awaiting)} patch(es) newest-first")
        ok = 0
        for entry in awaiting:
            if process_patch_entry(entry, workspace=workspace, api_key=api_key):
                ok += 1
        print(f"[healing] Completed {ok}/{len(awaiting)} patches")
        return 0 if ok == len(awaiting) else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
