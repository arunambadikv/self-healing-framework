"""Generate MCP repair prompts and stub patch proposals from failure reports."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from healing.healing_queue import (
    list_unprocessed_failures,
    load_failure_payload,
    mark_failure_not_healable,
    mark_failure_proposed,
)
from healing.failure_classifier import classify_failure, is_healable
from healing.locator_source import read_property_return_expression, resolve_page_path
from healing.paths import MANIFEST_JSON, QUEUE_PATCHES, ensure_queue_dirs


def new_patch_id() -> str:
    return f"P-{uuid.uuid4().hex[:12]}"


def _load_manifest(workspace: Path) -> dict[str, Any]:
    path = workspace / MANIFEST_JSON
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _architecture_context_for_ref(manifest: dict[str, Any], architecture_ref: str | None) -> dict[str, Any]:
    if not architecture_ref or "." not in architecture_ref:
        return {}
    page_class, _, locator_id = architecture_ref.partition(".")
    page_info = manifest.get("pages", {}).get(page_class, {})
    loc = page_info.get("locators", {}).get(locator_id, {})
    return {
        "page_class": page_class,
        "file": page_info.get("file"),
        "locator_id": locator_id,
        "locator": loc,
    }


def build_proposal_prompt(
    failure: dict[str, Any],
    *,
    manifest: dict[str, Any],
    base_url: str,
    patch_id: str,
) -> str:
    failure_id = failure["failure_id"]
    arch = _architecture_context_for_ref(manifest, failure.get("architecture_ref"))
    return f"""# Healing proposal task — {failure_id}

## Failure summary
- Test: `{failure['test']['nodeid']}`
- Error: `{failure['error']['type']}` — {failure['error']['message'][:400]}
- Architecture ref: `{failure.get('architecture_ref')}`
- Page URL: {failure.get('environment', {}).get('page_url')}

## Architecture context
```json
{json.dumps(arch, indent=2)}
```

## Steps before failure
{json.dumps(failure.get('test_steps', []), indent=2)}

## Required actions (Playwright MCP + Agent)
1. `browser_navigate` → {base_url}
2. `browser_snapshot` — find element for `{failure.get('architecture_ref')}`
3. Update the existing stub at `artifacts/healing-queue/patches/{patch_id}.json` (patch id `{patch_id}`)
4. Include `architecture_updates` targeting `pages/*.py` only (file, symbol, line, before, after)
5. Set `risk_level` (low/medium/high) and `validation_command`
6. Write matching `.md` human summary

## Skill
- `/playwright-locator-repair` (MCP diagnosis + P-*.json proposal shape)
"""


def write_stub_patch(
    failure: dict[str, Any],
    *,
    manifest: dict[str, Any],
    workspace: Path,
) -> tuple[str, Path, Path]:
    """Write agent task prompt + minimal stub; agent replaces stub via MCP."""
    patch_id = new_patch_id()
    failure_id = failure["failure_id"]
    arch_ctx = _architecture_context_for_ref(manifest, failure.get("architecture_ref"))
    file_path = arch_ctx.get("file") or "pages/demo_page.py"
    locator_id = arch_ctx.get("locator_id") or "unknown"
    loc = arch_ctx.get("locator") or {}
    page_path = resolve_page_path(workspace, file_path)
    before_expr = read_property_return_expression(page_path, locator_id)
    if not before_expr:
        before_expr = loc.get("expression", "TODO")

    proposal = {
        "patch_id": patch_id,
        "failure_id": failure_id,
        "classification": "selector_break",
        "patch_type": "pom_property",
        "risk_level": "medium",
        "risk_reason": "Locator failed during test; requires MCP verification before apply.",
        "architecture_updates": [
            {
                "file": file_path,
                "symbol": locator_id,
                "line": loc.get("line"),
                "change_type": "replace_locator",
                "before": before_expr,
                "after": "TODO: replace with MCP-verified Playwright expression",
            }
        ],
        "validation_command": f"{_python()} -m pytest {failure['test']['file']} -q",
        "links": {
            "failure_json": str((workspace / "artifacts/failures" / f"{failure_id}.json").resolve()),
            "failure_md": str((workspace / "artifacts/failures" / f"{failure_id}.md").resolve()),
        },
        "proposal_status": "awaiting_agent",
    }

    json_path = QUEUE_PATCHES / f"{patch_id}.json"
    md_path = QUEUE_PATCHES / f"{patch_id}.md"
    json_path.write_text(json.dumps({"proposal": proposal}, indent=2), encoding="utf-8")
    md_body = f"""# Patch proposal {patch_id}

**Failure:** [{failure_id}]({proposal['links']['failure_md']})
**Risk:** {proposal['risk_level']} — {proposal['risk_reason']}

## Suggested change (draft — verify with MCP)

- **File:** `{file_path}`
- **Locator:** `{locator_id}`
- **Before:** `{before_expr}`
- **After:** _pending MCP inspection_

## Validation

```bash
{proposal['validation_command']}
```

> Complete this patch via `/healing-propose` with Playwright MCP, then review with `/healing-review`.
"""
    md_path.write_text(md_body, encoding="utf-8")
    return patch_id, json_path, md_path


def _python() -> str:
    import sys

    return sys.executable


def process_failure_entry(entry: dict[str, Any], *, workspace: Path) -> str | None:
    failure_id = entry["failure_id"]
    failure = load_failure_payload(failure_id)
    classification = failure.get("classification") or classify_failure(failure)
    if not is_healable(failure):
        reason = f"Not healable ({classification}); skipping locator proposal."
        mark_failure_not_healable(failure_id, reason=reason)
        print(f"[skip] {failure_id}: {reason}")
        return None

    manifest = _load_manifest(workspace)
    base_url = failure.get("environment", {}).get("base_url", "https://seleniumbase.io/demo_page")

    patch_id, json_path, md_path = write_stub_patch(failure, manifest=manifest, workspace=workspace)
    prompt_path = QUEUE_PATCHES / f"{patch_id}-agent-task.md"
    prompt_path.write_text(
        build_proposal_prompt(
            failure, manifest=manifest, base_url=base_url, patch_id=patch_id
        ),
        encoding="utf-8",
    )

    mark_failure_proposed(failure_id, patch_id, patch_json=json_path, patch_md=md_path)
    return patch_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare healing proposals from failures.")
    parser.add_argument("--list", action="store_true", help="List unprocessed failures.")
    parser.add_argument("--process-all", action="store_true", help="Create stub patches for all pending.")
    parser.add_argument("--failure-id", help="Process single failure id.")
    parser.add_argument("--workspace", default=".", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    ensure_queue_dirs()

    if args.list:
        pending = list_unprocessed_failures()
        if not pending:
            print("No unprocessed failures.")
            return 0
        for entry in pending:
            print(f"- {entry['failure_id']} → {entry.get('failure_md')}")
        return 0

    if args.failure_id:
        entry = next(
            (e for e in list_unprocessed_failures() if e["failure_id"] == args.failure_id),
            None,
        )
        if entry is None:
            print(f"Failure not pending or unknown: {args.failure_id}")
            return 1
        patch_id = process_failure_entry(entry, workspace=workspace)
        if patch_id:
            print(f"Created patch {patch_id} (stub — complete via MCP propose runner)")
        return 0 if patch_id else 0

    if args.process_all:
        pending = list_unprocessed_failures()
        for entry in pending:
            patch_id = process_failure_entry(entry, workspace=workspace)
            if patch_id:
                print(f"[ok] {entry['failure_id']} → {patch_id} (awaiting_agent)")
            else:
                print(f"[skip] {entry['failure_id']} (not_healable)")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
