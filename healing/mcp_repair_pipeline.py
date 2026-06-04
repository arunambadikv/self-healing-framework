from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from healing.locator_inspector import (
    InspectionResult,
    probe_registry_candidates,
    rank_working_candidates,
)
from healing.agent_repair_stub import generate_mcp_repair_prompt
from healing.mcp_tools import build_mcp_repair_plan
from healing.patch_models import LocatorPatchResult
from healing.registry_updater import load_healing_report, suggest_registry_updates

SKILL_ROUTING = {
    "missing_key": ["playwright-locator-repair", "playwright-registry-update", "playwright-locator-patching"],
    "healed": ["playwright-registry-update", "playwright-locator-patching"],
    "failed": ["playwright-locator-repair", "playwright-registry-update", "playwright-locator-patching"],
    "promote_fallback": ["playwright-registry-update", "playwright-locator-patching"],
    "add_semantic_key": ["playwright-locator-repair", "playwright-registry-update", "playwright-locator-patching"],
}


@dataclass
class RepairTrigger:
    semantic_key: str
    trigger_type: str
    source_report: str
    action: str
    message: str
    registry_entry: dict[str, Any] | None = None
    suggested_entry: dict[str, Any] | None = None
    used_candidate: dict[str, Any] | None = None


@dataclass
class McpRepairBundle:
    semantic_key: str
    trigger_type: str
    base_url: str
    skill_routing: list[str]
    mcp_steps: list[str]
    mcp_plan: dict[str, Any]
    agent_prompt_markdown: str
    proposal: dict[str, Any]
    inspection: dict[str, Any] | None = None


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_registry(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def collect_triggers_from_report(
    report_path: Path,
    registry: dict[str, Any],
) -> list[RepairTrigger]:
    report = load_healing_report(report_path)
    triggers: list[RepairTrigger] = []
    seen: set[tuple[str, str]] = set()

    for event in report.get("events", []):
        key = event.get("key")
        status = event.get("status")
        if not key:
            continue

        if status == "healed":
            ttype = "healed"
        elif status == "failed":
            details = event.get("details") or {}
            ttype = details.get("classification", "failed")
            if ttype not in {"missing_key", "failed"}:
                ttype = "failed"
        elif status == "primary":
            details = event.get("details") or {}
            if (
                details.get("classification") == "add_semantic_key"
                and details.get("source") == "raw_learning"
            ):
                ttype = "add_semantic_key"
            else:
                continue
        else:
            continue

        dedupe = (key, ttype)
        if dedupe in seen:
            continue
        seen.add(dedupe)

        triggers.append(
            RepairTrigger(
                semantic_key=key,
                trigger_type=ttype,
                source_report=str(report_path),
                action=event.get("action", ""),
                message=event.get("message", ""),
                registry_entry=registry.get(key),
                suggested_entry=(event.get("details") or {}).get("suggested_registry_entry"),
                used_candidate=event.get("used_candidate"),
            )
        )

    for suggestion in suggest_registry_updates(report_path):
        dedupe = (suggestion.semantic_key, suggestion.change_type)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        triggers.append(
            RepairTrigger(
                semantic_key=suggestion.semantic_key,
                trigger_type=suggestion.change_type,
                source_report=str(report_path),
                action=registry.get(suggestion.semantic_key, {}).get("action", ""),
                message=suggestion.reason,
                registry_entry=registry.get(suggestion.semantic_key),
                suggested_entry=suggestion.suggested_candidate,
                used_candidate=suggestion.suggested_candidate,
            )
        )

    return triggers


def collect_triggers(
    reports_dir: Path,
    registry: dict[str, Any],
    ignore_globs: list[str] | None = None,
) -> list[RepairTrigger]:
    all_triggers: list[RepairTrigger] = []
    if not reports_dir.exists():
        return all_triggers
    ignore_globs = ignore_globs or []
    for report_path in sorted(reports_dir.glob("*.json")):
        if any(fnmatch.fnmatch(report_path.name, pattern) for pattern in ignore_globs):
            continue
        all_triggers.extend(collect_triggers_from_report(report_path, registry))
    return all_triggers


def _mcp_steps_for_trigger(trigger: RepairTrigger, base_url: str) -> list[str]:
    return [
        f"1. browser_navigate url={base_url}",
        "2. browser_snapshot (capture accessibility tree)",
        f"3. Inspect element intent for semantic key: {trigger.semantic_key}",
        "4. Propose locators in priority order: test_id → role → label → placeholder → text → css",
        "5. Update locator_registry.yaml only (do not weaken assertions or rewrite tests)",
        f"6. Return LocatorPatchResult JSON with validation_command for key {trigger.semantic_key}",
    ]


def _build_agent_prompt(trigger: RepairTrigger, base_url: str, inspection: InspectionResult | None) -> str:
    intent = "No intent specified"
    if trigger.registry_entry:
        intent = trigger.registry_entry.get("intent", intent)
    elif trigger.suggested_entry:
        intent = trigger.suggested_entry.get("intent", intent)

    prompt = generate_mcp_repair_prompt(
        semantic_key=trigger.semantic_key,
        action=trigger.action or "unknown",
        intent=intent,
        base_url=base_url,
        last_error=trigger.message,
        registry_entry=trigger.registry_entry,
        trigger_type=trigger.trigger_type,
    )
    extras = [
        "",
        "## Healing report context",
        f"- source_report: `{trigger.source_report}`",
        f"- trigger_type: `{trigger.trigger_type}`",
        "",
        "## Skill routing",
        *[f"- `{s}`" for s in SKILL_ROUTING.get(trigger.trigger_type, SKILL_ROUTING["failed"])],
        "",
        "## Registry context",
        "```json",
        json.dumps(trigger.registry_entry, indent=2),
        "```",
    ]
    if trigger.suggested_entry:
        extras.extend(
            [
                "",
                "## Suggested entry / promotion candidate",
                "```json",
                json.dumps(trigger.suggested_entry, indent=2),
                "```",
            ]
        )
    if trigger.used_candidate:
        extras.extend(
            [
                "",
                "## Used candidate from healing event",
                "```json",
                json.dumps(trigger.used_candidate, indent=2),
                "```",
            ]
        )
    if inspection:
        extras.extend(
            [
                "",
                "## Programmatic inspection (local Playwright probe)",
                "```json",
                json.dumps(
                    {
                        "probes": [asdict(p) for p in inspection.probes],
                        "accessibility_hint": inspection.accessibility_hint,
                        "ranked_working": rank_working_candidates(inspection.probes),
                    },
                    indent=2,
                ),
                "```",
            ]
        )
    extras.extend(
        [
            "",
            "## Alternative apply (healing report suggestion)",
            "```bash",
            f"python -m healing.apply_suggestion --report {trigger.source_report} "
            f"--key {trigger.semantic_key} --change-type {trigger.trigger_type} --apply",
            "```",
        ]
    )
    return prompt + "\n".join(extras)


def _default_proposal(trigger: RepairTrigger, base_url: str) -> LocatorPatchResult:
    if trigger.trigger_type == "add_semantic_key":
        patch_type = "registry_only"
        classification = "selector_break"
        patch = yaml.safe_dump(
            {trigger.semantic_key: trigger.suggested_entry or {}},
            sort_keys=False,
        )
    elif trigger.trigger_type in {"healed", "promote_fallback"}:
        patch_type = "registry_only"
        classification = "selector_break"
        entry = trigger.registry_entry or {}
        preferred = list(entry.get("preferred", []))
        if trigger.used_candidate and isinstance(trigger.used_candidate, dict):
            preferred = [trigger.used_candidate] + [
                c for c in preferred if c != trigger.used_candidate
            ]
        patch = yaml.safe_dump(
            {trigger.semantic_key: {**entry, "preferred": preferred}},
            sort_keys=False,
        )
    else:
        patch_type = "no_patch"
        classification = "unknown"
        patch = "# MCP/agent inspection required before patch."

    return LocatorPatchResult(
        classification=classification,
        patch_type=patch_type,
        semantic_key=trigger.semantic_key,
        confidence=0.75 if trigger.trigger_type in {"healed", "promote_fallback"} else 0.5,
        reason=trigger.message,
        files_changed=["locator_registry.yaml"],
        validation_command=f"pytest -q -k {trigger.semantic_key.replace('.', '_')}",
        patch=patch,
    )


def build_repair_bundle(
    trigger: RepairTrigger,
    *,
    base_url: str,
    inspection: InspectionResult | None = None,
) -> McpRepairBundle:
    skills = SKILL_ROUTING.get(trigger.trigger_type, SKILL_ROUTING["failed"])
    proposal = _default_proposal(trigger, base_url)
    intent = (trigger.registry_entry or {}).get("intent", f"Repair {trigger.semantic_key}")
    mcp_plan = build_mcp_repair_plan(
        base_url=base_url,
        semantic_key=trigger.semantic_key,
        action=trigger.action or "unknown",
        intent=intent,
        registry_entry=trigger.registry_entry,
    )
    return McpRepairBundle(
        semantic_key=trigger.semantic_key,
        trigger_type=trigger.trigger_type,
        base_url=base_url,
        skill_routing=skills,
        mcp_steps=_mcp_steps_for_trigger(trigger, base_url),
        mcp_plan=mcp_plan,
        agent_prompt_markdown=_build_agent_prompt(trigger, base_url, inspection),
        proposal=asdict(proposal),
        inspection=asdict(inspection) if inspection else None,
    )


def generate_bundles_for_report(
    report_path: Path,
    *,
    registry_path: Path,
    output_dir: Path,
    base_url: str,
    inspect: bool = False,
) -> int:
    """Generate MCP repair bundles for a single healing report (e.g. after one test)."""
    registry = _load_registry(registry_path)
    triggers = collect_triggers_from_report(report_path.resolve(), registry)
    if not triggers:
        return 0

    workspace = report_path.parent.parent
    return _write_bundles_for_triggers(
        triggers=triggers,
        workspace=workspace,
        registry_path=registry_path,
        output_dir=output_dir,
        base_url=base_url,
        inspect=inspect,
    )


def _write_bundles_for_triggers(
    *,
    triggers: list[RepairTrigger],
    workspace: Path,
    registry_path: Path,
    output_dir: Path,
    base_url: str,
    inspect: bool,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir = output_dir / "prompts"
    proposals_dir = output_dir / "proposals"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    proposals_dir.mkdir(parents=True, exist_ok=True)

    page = None
    browser = None
    playwright = None
    if inspect:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(base_url, wait_until="domcontentloaded")

    bundles: list[dict[str, Any]] = []
    try:
        for trigger in triggers:
            inspection = None
            if inspect and page and trigger.registry_entry:
                inspection = probe_registry_candidates(
                    page,
                    semantic_key=trigger.semantic_key,
                    registry_entry=trigger.registry_entry,
                    base_url=base_url,
                )

            bundle = build_repair_bundle(trigger, base_url=base_url, inspection=inspection)
            slug = trigger.semantic_key.replace(".", "_")
            prompt_path = prompts_dir / f"{slug}__{trigger.trigger_type}.md"
            plan_path = output_dir / "mcp-plans" / f"{slug}__{trigger.trigger_type}.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps(bundle.mcp_plan, indent=2), encoding="utf-8")
            prompt_path.write_text(bundle.agent_prompt_markdown, encoding="utf-8")

            proposal_path = proposals_dir / f"{slug}__{trigger.trigger_type}.json"
            proposal_path.write_text(
                json.dumps(
                    {
                        "bundle": asdict(bundle),
                        "proposal": bundle.proposal,
                        "mcp_plan_file": str(plan_path),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            bundles.append(
                {
                    "semantic_key": trigger.semantic_key,
                    "trigger_type": trigger.trigger_type,
                    "prompt_file": str(prompt_path),
                }
            )
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()

    return len(bundles)


def run_mcp_repair_pipeline(
    *,
    workspace: Path,
    reports_dir: Path,
    registry_path: Path,
    output_dir: Path,
    base_url: str,
    inspect: bool,
) -> int:
    config = _load_config(workspace / "healing/ci_gates_config.yaml")
    ignore_globs = (config.get("thresholds") or {}).get("ignore_report_globs", [])
    registry = _load_registry(registry_path)
    triggers = collect_triggers(reports_dir, registry, ignore_globs=ignore_globs)
    if not triggers:
        print("No repair triggers found in healing reports.")
        return 0

    count = _write_bundles_for_triggers(
        triggers=triggers,
        workspace=workspace,
        registry_path=registry_path,
        output_dir=output_dir,
        base_url=base_url,
        inspect=inspect,
    )
    print(f"Wrote {count} repair bundle(s) to {output_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase B: build MCP-assisted repair bundles from healing reports."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root.")
    parser.add_argument(
        "--reports-dir",
        default="artifacts/healing-reports",
        help="Healing reports directory.",
    )
    parser.add_argument("--registry", default="locator_registry.yaml")
    parser.add_argument(
        "--output-dir",
        default="artifacts/mcp-repair-bundles",
        help="Output directory for prompts and proposals.",
    )
    parser.add_argument(
        "--config",
        default="healing/ci_gates_config.yaml",
        help="Config file for default base URL.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override base URL for MCP navigation.",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Run Playwright probe + accessibility snapshot hints (no MCP server required).",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Process only this report file instead of all reports in reports-dir.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    config = _load_config(workspace / args.config)
    mcp_cfg = config.get("mcp_repair", {})
    base_url = args.base_url or mcp_cfg.get(
        "default_base_url", "https://seleniumbase.io/demo_page"
    )
    output_dir = workspace / (args.output_dir or mcp_cfg.get("output_dir", "artifacts/mcp-repair-bundles"))
    registry_path = workspace / args.registry

    if args.report:
        reports_dir = Path(args.report).parent
        registry = _load_registry(registry_path)
        triggers = collect_triggers_from_report(Path(args.report).resolve(), registry)
        if not triggers:
            print("No triggers in specified report.")
            return 0
        # reuse run logic for single report - simplify by writing temp approach
        output_dir.mkdir(parents=True, exist_ok=True)
        for trigger in triggers:
            bundle = build_repair_bundle(trigger, base_url=base_url)
            slug = trigger.semantic_key.replace(".", "_")
            (output_dir / "prompts").mkdir(parents=True, exist_ok=True)
            (output_dir / "proposals").mkdir(parents=True, exist_ok=True)
            p = output_dir / "prompts" / f"{slug}__{trigger.trigger_type}.md"
            p.write_text(bundle.agent_prompt_markdown, encoding="utf-8")
            print(f"Bundle: {trigger.semantic_key} -> {p}")
        return 0

    return run_mcp_repair_pipeline(
        workspace=workspace,
        reports_dir=workspace / args.reports_dir,
        registry_path=registry_path,
        output_dir=output_dir,
        base_url=base_url,
        inspect=args.inspect,
    )


if __name__ == "__main__":
    raise SystemExit(main())
