from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from healing.agent_repair_stub import generate_mcp_repair_prompt
from healing.patch_models import LocatorPatchResult
from healing.registry_updater import load_healing_report, suggest_registry_updates

SKILL_FILE_MAP = {
    "playwright-locator-repair": Path("skills/playwright-locator-repair/SKILL.md"),
    "playwright-registry-update": Path("skills/playwright-registry-update/SKILL.md"),
    "playwright-locator-patching": Path("skills/playwright-locator-patching/SKILL.md"),
}


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    raise ValueError(f"Expected mapping at '{path}', got {type(data).__name__}.")


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _compose_registry_patch_preview(
    registry: dict[str, Any],
    semantic_key: str,
    change_type: str,
    suggested_candidate: dict[str, Any] | None,
) -> str:
    if change_type == "add_semantic_key":
        payload = {semantic_key: suggested_candidate or {}}
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)

    if change_type == "promote_fallback":
        entry = deepcopy(registry.get(semantic_key, {}))
        if not isinstance(entry, dict):
            entry = {}
        preferred = list(entry.get("preferred", []))
        fallback = list(entry.get("fallback", []))
        if isinstance(suggested_candidate, dict):
            preferred = [suggested_candidate] + [
                item for item in preferred if item != suggested_candidate
            ]
            fallback = [item for item in fallback if item != suggested_candidate]
        entry["preferred"] = preferred
        entry["fallback"] = fallback
        payload = {semantic_key: entry}
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)

    return "# No automatic patch preview available."


def _load_skill_texts(workspace_root: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    for skill_name, relative_path in SKILL_FILE_MAP.items():
        path = workspace_root / relative_path
        if path.exists():
            texts[skill_name] = path.read_text(encoding="utf-8")
        else:
            texts[skill_name] = f"# Missing skill file: {relative_path}"
    return texts


def _build_prompt_for_suggestion(
    *,
    report_path: Path,
    semantic_key: str,
    change_type: str,
    reason: str,
    confidence: float,
    suggested_candidate: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
    registry_patch_preview: str,
    skill_texts: dict[str, str],
) -> tuple[str, list[str]]:
    primary_skill = "playwright-registry-update"
    companion_skills = ["playwright-locator-patching"]
    all_skills = [primary_skill] + companion_skills

    prompt = [
        "# Agent Task: Registry Suggestion Review",
        "",
        f"- report: `{report_path}`",
        f"- semantic key: `{semantic_key}`",
        f"- change type: `{change_type}`",
        f"- suggestion confidence: `{confidence}`",
        f"- reason: {reason}",
        "",
        "## Context",
        "Current registry entry:",
        "```json",
        _json_dump(registry_entry),
        "```",
        "Suggested candidate/entry:",
        "```json",
        _json_dump(suggested_candidate),
        "```",
        "Proposed YAML patch preview:",
        "```yaml",
        registry_patch_preview.rstrip(),
        "```",
        "",
        "## Required Skill Routing",
        f"- Primary skill: `{primary_skill}`",
        f"- Companion skills: `{', '.join(companion_skills)}`",
        "",
        "## Task",
        "Use the provided skills to review whether this registry patch is safe and correct.",
        "Do not weaken assertions and do not change test intent.",
        "Return a JSON payload shaped like `LocatorPatchResult`.",
        "",
        "## Skill: playwright-registry-update",
        skill_texts.get("playwright-registry-update", ""),
        "",
        "## Skill: playwright-locator-patching",
        skill_texts.get("playwright-locator-patching", ""),
    ]
    return "\n".join(prompt), all_skills


def _build_prompt_for_failed_event(
    *,
    report_path: Path,
    event: dict[str, Any],
    registry_entry: dict[str, Any] | None,
    skill_texts: dict[str, str],
) -> tuple[str, list[str]]:
    semantic_key = event.get("key")
    repair_prompt = generate_mcp_repair_prompt(
        semantic_key=str(semantic_key),
        action=str(event.get("action", "unknown")),
        intent=f"Repair locator for {semantic_key}",
        base_url="https://seleniumbase.io/demo_page",
        last_error=event.get("message", "unknown failure"),
        registry_entry=registry_entry,
        trigger_type="failed",
    )
    primary_skill = "playwright-locator-repair"
    companion_skills = ["playwright-registry-update", "playwright-locator-patching"]
    all_skills = [primary_skill] + companion_skills

    prompt = [
        "# Agent Task: Failed Locator Investigation",
        "",
        f"- report: `{report_path}`",
        f"- semantic key: `{semantic_key}`",
        f"- action: `{event.get('action')}`",
        f"- status: `{event.get('status')}`",
        "",
        "## Failure Event",
        "```json",
        _json_dump(event),
        "```",
        "Current registry entry:",
        "```json",
        _json_dump(registry_entry),
        "```",
        "",
        "## Repair Prompt",
        "```text",
        repair_prompt,
        "```",
        "",
        "## Required Skill Routing",
        f"- Primary skill: `{primary_skill}`",
        f"- Companion skills: `{', '.join(companion_skills)}`",
        "",
        "Return a JSON payload shaped like `LocatorPatchResult`.",
        "",
        "## Skill: playwright-locator-repair",
        skill_texts.get("playwright-locator-repair", ""),
        "",
        "## Skill: playwright-registry-update",
        skill_texts.get("playwright-registry-update", ""),
        "",
        "## Skill: playwright-locator-patching",
        skill_texts.get("playwright-locator-patching", ""),
    ]
    return "\n".join(prompt), all_skills


def _default_result_for_suggestion(
    *,
    semantic_key: str,
    change_type: str,
    reason: str,
    confidence: float,
    patch_preview: str,
) -> LocatorPatchResult:
    return LocatorPatchResult(
        classification="selector_break",
        patch_type="registry_only",
        semantic_key=semantic_key,
        confidence=confidence,
        reason=reason,
        files_changed=["locator_registry.yaml"],
        validation_command=f"pytest -q tests/test_demo_buttons_links.py",
        patch=patch_preview,
    )


def _default_result_for_failed_event(event: dict[str, Any]) -> LocatorPatchResult:
    return LocatorPatchResult(
        classification="unknown",
        patch_type="no_patch",
        semantic_key=event.get("key"),
        confidence=0.0,
        reason=event.get("message", "Locator action failed."),
        files_changed=[],
        validation_command="pytest -q",
        patch="# Investigation required.",
    )


def _state_key_for(path: Path) -> str:
    return str(path.resolve())


def _load_state(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {str(k): float(v) for k, v in data.items()}
    return {}


def _save_state(path: Path, state: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(state), encoding="utf-8")


def _iter_new_reports(reports_dir: Path, state: dict[str, float], process_all: bool) -> list[Path]:
    report_files = sorted(reports_dir.glob("*.json"))
    if process_all:
        return report_files

    new_items: list[Path] = []
    for report in report_files:
        key = _state_key_for(report)
        mtime = report.stat().st_mtime
        if state.get(key) != mtime:
            new_items.append(report)
    return new_items


def _write_prompt(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_agent_runner(
    *,
    workspace_root: Path,
    reports_dir: Path,
    registry_path: Path,
    prompts_dir: Path,
    proposals_dir: Path,
    state_path: Path,
    process_all: bool,
) -> int:
    if not reports_dir.exists():
        print(f"No reports directory found: {reports_dir}")
        return 0

    registry = _load_yaml(registry_path)
    state = _load_state(state_path)
    report_files = _iter_new_reports(reports_dir, state, process_all)
    if not report_files:
        print("No new healing reports to process.")
        return 0

    skill_texts = _load_skill_texts(workspace_root)
    proposals_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    processed_count = 0
    for report_path in report_files:
        report = load_healing_report(report_path)
        suggestions = suggest_registry_updates(report_path)
        report_stem = report_path.stem

        proposals: list[dict[str, Any]] = []
        prompt_index = 1

        # Build skill prompts for deterministic suggestion types first.
        for suggestion in suggestions:
            semantic_key = suggestion.semantic_key
            registry_entry = registry.get(semantic_key)
            patch_preview = _compose_registry_patch_preview(
                registry=registry,
                semantic_key=semantic_key,
                change_type=suggestion.change_type,
                suggested_candidate=suggestion.suggested_candidate,
            )
            prompt_text, skill_names = _build_prompt_for_suggestion(
                report_path=report_path,
                semantic_key=semantic_key,
                change_type=suggestion.change_type,
                reason=suggestion.reason,
                confidence=suggestion.confidence,
                suggested_candidate=suggestion.suggested_candidate,
                registry_entry=registry_entry,
                registry_patch_preview=patch_preview,
                skill_texts=skill_texts,
            )
            prompt_file = (
                prompts_dir
                / f"{report_stem}__{prompt_index:02d}__{_slug(semantic_key)}__{suggestion.change_type}.md"
            )
            _write_prompt(prompt_file, prompt_text)
            prompt_index += 1

            result = _default_result_for_suggestion(
                semantic_key=semantic_key,
                change_type=suggestion.change_type,
                reason=suggestion.reason,
                confidence=suggestion.confidence,
                patch_preview=patch_preview,
            )
            proposal = asdict(result)
            proposal["skill_routing"] = skill_names
            proposal["source_report"] = str(report_path)
            proposal["source_change_type"] = suggestion.change_type
            proposal["prompt_file"] = str(prompt_file)
            proposals.append(proposal)

        # Build investigation prompts for failed events not covered by suggestions.
        covered_keys = {item.semantic_key for item in suggestions}
        for event in report.get("events", []):
            if event.get("status") != "failed":
                continue
            semantic_key = event.get("key")
            if semantic_key in covered_keys:
                continue

            registry_entry = registry.get(semantic_key)
            prompt_text, skill_names = _build_prompt_for_failed_event(
                report_path=report_path,
                event=event,
                registry_entry=registry_entry,
                skill_texts=skill_texts,
            )
            prompt_file = (
                prompts_dir
                / f"{report_stem}__{prompt_index:02d}__{_slug(str(semantic_key))}__failed.md"
            )
            _write_prompt(prompt_file, prompt_text)
            prompt_index += 1

            result = _default_result_for_failed_event(event)
            proposal = asdict(result)
            proposal["skill_routing"] = skill_names
            proposal["source_report"] = str(report_path)
            proposal["source_change_type"] = "failed_investigation"
            proposal["prompt_file"] = str(prompt_file)
            proposals.append(proposal)

        proposal_file = proposals_dir / f"{report_stem}.json"
        proposal_payload = {
            "report": str(report_path),
            "proposal_count": len(proposals),
            "proposals": proposals,
        }
        proposal_file.write_text(_json_dump(proposal_payload), encoding="utf-8")
        print(f"Generated {len(proposals)} proposal(s): {proposal_file}")

        state[_state_key_for(report_path)] = report_path.stat().st_mtime
        processed_count += 1

    _save_state(state_path, state)
    print(f"Processed {processed_count} report(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read new healing reports, route each issue to the appropriate skill prompt, "
            "and output reviewable patch proposals (no registry mutation)."
        )
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root path (default: current directory).",
    )
    parser.add_argument(
        "--reports-dir",
        default="artifacts/healing-reports",
        help="Directory containing healing report JSON files.",
    )
    parser.add_argument(
        "--registry",
        default="locator_registry.yaml",
        help="Path to locator registry YAML.",
    )
    parser.add_argument(
        "--prompts-dir",
        default="artifacts/agent-prompts",
        help="Directory for generated agent prompt markdown files.",
    )
    parser.add_argument(
        "--proposals-dir",
        default="artifacts/agent-proposals",
        help="Directory for generated patch proposal JSON files.",
    )
    parser.add_argument(
        "--state-file",
        default="artifacts/agent-proposals/.agent-runner-state.json",
        help="State file used to track already processed reports.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all reports, not just new/modified ones.",
    )
    args = parser.parse_args()

    workspace_root = Path(args.workspace).resolve()
    return run_agent_runner(
        workspace_root=workspace_root,
        reports_dir=(workspace_root / args.reports_dir).resolve(),
        registry_path=(workspace_root / args.registry).resolve(),
        prompts_dir=(workspace_root / args.prompts_dir).resolve(),
        proposals_dir=(workspace_root / args.proposals_dir).resolve(),
        state_path=(workspace_root / args.state_file).resolve(),
        process_all=args.all,
    )


if __name__ == "__main__":
    raise SystemExit(main())
