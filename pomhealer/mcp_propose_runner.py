"""Complete healing patch proposals via LLM provider + Playwright MCP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pomhealer.queue import (
    is_patch_complete,
    list_awaiting_agent,
    load_failure_payload,
    select_latest_awaiting_patches,
)
from pomhealer.llm_config import LlmConfig, missing_key_message, resolve_llm_config
from pomhealer.paths import QUEUE_PATCHES, ensure_queue_dirs
from pomhealer.skill_paths import load_skill_text


def resolve_storage_state_path(failure: dict[str, Any], workspace: Path) -> Path | None:
    """Return absolute path to failure storage_state if it exists on disk."""
    raw = (failure.get("artifacts") or {}).get("storage_state")
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = workspace / path
    return path if path.exists() else None


def _format_propose_error(exc: BaseException) -> str:
    """Unwrap ExceptionGroup / TaskGroup so the real API or MCP error is visible."""
    parts: list[str] = [str(exc).strip() or type(exc).__name__]
    sub = getattr(exc, "exceptions", None)
    if sub:
        for inner in sub:
            parts.append(_format_propose_error(inner))
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        parts.append(_format_propose_error(cause))
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return " | ".join(seen)


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
2. Update `{patch_rel}` — replace TODO in `architecture_updates[].after` with a **different** locator than `before` (no-op copies are invalid).
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
    config: LlmConfig | None = None,
) -> str:
    """Back-compat wrapper: run propose with resolved or explicit Cursor-style config."""
    from pomhealer.propose_providers import get_provider

    if config is None:
        config = resolve_llm_config()
        if api_key:
            config = LlmConfig(
                provider=config.provider,
                api_key=api_key,
                model=config.model,
                key_env=config.key_env,
            )
    provider = get_provider(config)
    return provider.run_propose(
        prompt, workspace=workspace, config=config, storage_state=storage_state
    )


def process_patch_entry(
    entry: dict[str, Any],
    *,
    workspace: Path,
    api_key: str | None = None,
    config: LlmConfig | None = None,
) -> bool:
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
        from pomhealer.patch_promote import promote_patch

        promote_patch(patch_id)
        print(f"[ok] {patch_id} already complete → patch_ready")
        return True

    if config is None:
        config = resolve_llm_config()
        if api_key:
            # Legacy callers that only passed CURSOR_API_KEY
            config = LlmConfig(
                provider=config.provider,
                api_key=api_key,
                model=config.model,
                key_env=config.key_env,
            )

    if not config.has_key:
        print(f"[error] {patch_id}: {missing_key_message(config)}")
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
        print(f"[pomhealer] Using storage_state for {patch_id}: {storage_state}")
    else:
        print(f"[pomhealer] No storage_state for {patch_id} — agent will use page_url / step replay")

    prompt = build_agent_prompt(entry, workspace, storage_state=storage_state)
    print(
        f"[pomhealer] Running {config.provider} + Playwright MCP for {patch_id} "
        f"(model={config.model})..."
    )
    try:
        from pomhealer.propose_providers import get_provider

        summary = get_provider(config).run_propose(
            prompt,
            workspace=workspace,
            config=config,
            storage_state=storage_state,
        )
        print(f"[pomhealer] Agent: {summary[:200]}")
    except Exception as exc:
        print(f"[error] Propose failed for {patch_id}: {_format_propose_error(exc)}")
        return False

    payload = json.loads(patch_path.read_text(encoding="utf-8"))
    proposal = payload.get("proposal") or payload
    if not is_patch_complete(proposal, workspace=workspace, check_source=True):
        from pomhealer.patch_validate import validate_proposal

        errs = validate_proposal(proposal, workspace=workspace, check_source=True)
        print(
            f"[error] {patch_id} still incomplete after agent run: "
            + ("; ".join(errs) if errs else "TODO remains")
        )
        return False

    from pomhealer.patch_promote import promote_patch

    promote_patch(patch_id)
    print(f"[ok] {patch_id} → patch_ready")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Complete healing patches via LLM provider + Playwright MCP."
    )
    parser.add_argument("--list", action="store_true", help="List patches awaiting agent.")
    parser.add_argument("--process-all", action="store_true", help="Process all awaiting_agent patches.")
    parser.add_argument("--patch-id", help="Process single patch id.")
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit JSON for --list.")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    from pomhealer.paths import configure_workspace

    configure_workspace(workspace)
    ensure_queue_dirs()

    from pomhealer.doctor import load_dotenv_files
    from pomhealer.package_sync import refresh_packaged_assets_if_stale

    load_dotenv_files(workspace)
    refresh_packaged_assets_if_stale(workspace)

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

    config = resolve_llm_config()

    if args.patch_id:
        entry = next(
            (e for e in list_awaiting_agent() if e.get("patch_id") == args.patch_id),
            None,
        )
        if entry is None:
            print(f"Patch not awaiting agent: {args.patch_id}")
            return 1
        return 0 if process_patch_entry(entry, workspace=workspace, config=config) else 1

    if args.process_all:
        awaiting = select_latest_awaiting_patches()
        all_awaiting = list_awaiting_agent()
        skipped = len(all_awaiting) - len(awaiting)
        if not awaiting:
            print("No patches awaiting agent.")
            return 0
        if skipped:
            print(
                f"[pomhealer] Processing {len(awaiting)} latest patch(es) "
                f"(skipped {skipped} older duplicate architecture_ref)"
            )
        else:
            print(f"[pomhealer] Processing {len(awaiting)} patch(es) newest-first")
        print(f"[pomhealer] Provider={config.provider} model={config.model}")
        ok = 0
        for entry in awaiting:
            if process_patch_entry(entry, workspace=workspace, config=config):
                ok += 1
        print(f"[pomhealer] Completed {ok}/{len(awaiting)} patches")
        return 0 if ok == len(awaiting) else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
