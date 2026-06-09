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
    mark_patch_ready,
)
from healing.paths import QUEUE_PATCHES, ensure_queue_dirs
from healing.skill_paths import load_skill_text


def _load_mcp_servers(workspace: Path) -> dict[str, Any]:
    """Load Playwright MCP stdio config from .cursor/mcp.json."""
    from cursor_sdk import StdioMcpServerConfig

    mcp_path = workspace / ".cursor" / "mcp.json"
    if mcp_path.exists():
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") or {}
        playwright = servers.get("playwright") or servers.get("project-0-playwright-healing-framework-playwright")
        if playwright and playwright.get("command"):
            return {
                "playwright": StdioMcpServerConfig(
                    command=playwright["command"],
                    args=list(playwright.get("args") or []),
                    env=dict(playwright.get("env") or {}),
                )
            }
    return {
        "playwright": StdioMcpServerConfig(
            command="npx",
            args=["@playwright/mcp@latest"],
        )
    }


def build_agent_prompt(entry: dict[str, Any], workspace: Path) -> str:
    patch_id = entry.get("patch_id", "")
    task_path = QUEUE_PATCHES / f"{patch_id}-agent-task.md"
    if task_path.exists():
        task_text = task_path.read_text(encoding="utf-8")
    else:
        task_text = f"Complete patch {patch_id} for failure {entry.get('failure_id')}."

    skill_text = load_skill_text("playwright-locator-repair")
    patch_json = QUEUE_PATCHES / f"{patch_id}.json"
    return f"""{skill_text}

---

# Automated MCP propose task

{task_text}

## Instructions

1. Use Playwright MCP (`browser_navigate`, `browser_snapshot`) to verify the correct locator.
2. Update `{patch_json.relative_to(workspace)}` — replace TODO in `architecture_updates[].after`.
3. Update matching `{patch_id}.md` with human-readable summary.
4. Set `proposal_status` to `"complete"` (remove `"awaiting_agent"`).
5. Set accurate `risk_level`, `risk_reason`, and `validation_command`.
6. Do NOT apply changes to `pages/*.py` — human review applies patches later.

Return a one-line summary when done.
"""


def run_sdk_propose(prompt: str, *, workspace: Path, api_key: str) -> str:
    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

    mcp_servers = _load_mcp_servers(workspace)
    result = Agent.prompt(
        prompt,
        AgentOptions(
            api_key=api_key,
            model="composer-2.5",
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
    if is_patch_complete(proposal):
        mark_patch_ready(patch_id)
        print(f"[ok] {patch_id} already complete → patch_ready")
        return True

    if not api_key:
        print(
            f"[error] {patch_id}: CURSOR_API_KEY required for MCP propose runner.\n"
            "  Install: pip install cursor-sdk (in project venv)\n"
            "  Export:  export CURSOR_API_KEY=cursor_..."
        )
        return False

    prompt = build_agent_prompt(entry, workspace)
    print(f"[healing] Running SDK + Playwright MCP for {patch_id}...")
    try:
        summary = run_sdk_propose(prompt, workspace=workspace, api_key=api_key)
        print(f"[healing] Agent: {summary[:200]}")
    except Exception as exc:
        print(f"[error] SDK propose failed for {patch_id}: {exc}")
        return False

    payload = json.loads(patch_path.read_text(encoding="utf-8"))
    proposal = payload.get("proposal") or payload
    if not is_patch_complete(proposal):
        print(f"[error] {patch_id} still incomplete after agent run (TODO remains)")
        return False

    mark_patch_ready(patch_id)
    from healing.healing_reports import emit_patch_ready

    emit_patch_ready(patch_id, proposal)
    print(f"[ok] {patch_id} → patch_ready")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete healing patches via Cursor SDK + Playwright MCP.")
    parser.add_argument("--list", action="store_true", help="List patches awaiting agent.")
    parser.add_argument("--process-all", action="store_true", help="Process all awaiting_agent patches.")
    parser.add_argument("--patch-id", help="Process single patch id.")
    parser.add_argument("--workspace", default=".", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    ensure_queue_dirs()

    if args.list:
        awaiting = list_awaiting_agent()
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
        awaiting = list_awaiting_agent()
        if not awaiting:
            print("No patches awaiting agent.")
            return 0
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
