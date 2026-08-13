from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from healing.test_policy import check_test_policy


@dataclass
class GateConfig:
    ignore_report_globs: list[str] = field(default_factory=list)
    max_failed_events: int = 0
    max_healed_ratio_warn: float = 0.10
    max_healed_ratio_fail: float = 0.30
    min_events_for_ratio: int = 1
    repeat_healed_key_warn: int = 2
    test_policy_enabled: bool = True
    test_policy_allowlist: list[str] = field(default_factory=list)
    test_policy_forbidden_patterns: list[str] = field(default_factory=list)
    require_pom_usage: bool = True
    test_policy_raw_mode: str = "error"
    require_architecture_manifest: bool = True
    max_unprocessed_failures: int = 0
    max_patch_ready_without_review: int = 10
    max_awaiting_agent: int = 5


@dataclass
class HealingAggregate:
    total_events: int = 0
    primary: int = 0
    healed: int = 0
    failed: int = 0
    healed_keys_by_report: dict[str, list[str]] = field(default_factory=dict)
    failed_events: list[dict[str, Any]] = field(default_factory=list)


def load_gate_config(path: Path) -> GateConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return gate_config_from_raw(raw)


def gate_config_from_raw(raw: dict[str, Any]) -> GateConfig:
    thresholds = raw.get("thresholds", {})
    policy = raw.get("test_policy", {})
    return GateConfig(
        ignore_report_globs=list(thresholds.get("ignore_report_globs", [])),
        max_failed_events=int(thresholds.get("max_failed_events", 0)),
        max_healed_ratio_warn=float(thresholds.get("max_healed_ratio_warn", 0.10)),
        max_healed_ratio_fail=float(thresholds.get("max_healed_ratio_fail", 0.30)),
        min_events_for_ratio=int(thresholds.get("min_events_for_ratio", 1)),
        repeat_healed_key_warn=int(thresholds.get("repeat_healed_key_warn", 2)),
        test_policy_enabled=bool(policy.get("enabled", True)),
        test_policy_allowlist=list(policy.get("allowlist", [])),
        test_policy_forbidden_patterns=list(policy.get("forbidden_patterns", [])),
        require_pom_usage=bool(policy.get("require_pom_usage", True)),
        test_policy_raw_mode=str(policy.get("raw_mode", "error")),
        require_architecture_manifest=bool(
            raw.get("architecture", {}).get("require_manifest", True)
        ),
        max_unprocessed_failures=int(thresholds.get("max_unprocessed_failures", 0)),
        max_patch_ready_without_review=int(
            thresholds.get("max_patch_ready_without_review", 10)
        ),
        max_awaiting_agent=int(thresholds.get("max_awaiting_agent", 5)),
    )


def _should_ignore_report(report_name: str, ignore_globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(report_name, pattern) for pattern in ignore_globs)


def aggregate_healing_reports(
    reports_dir: Path, ignore_globs: list[str] | None = None
) -> HealingAggregate:
    aggregate = HealingAggregate()
    if not reports_dir.exists():
        return aggregate

    ignore_globs = ignore_globs or []
    for report_path in sorted(reports_dir.glob("*.json")):
        if _should_ignore_report(report_path.name, ignore_globs):
            continue
        data = json.loads(report_path.read_text(encoding="utf-8"))
        report_name = report_path.name
        healed_keys: list[str] = []

        for event in data.get("events", []):
            aggregate.total_events += 1
            status = event.get("status")
            if status == "primary":
                aggregate.primary += 1
            elif status == "healed":
                aggregate.healed += 1
                healed_keys.append(event.get("key", ""))
            elif status == "failed":
                aggregate.failed += 1
                aggregate.failed_events.append(
                    {
                        "report": report_name,
                        "key": event.get("key"),
                        "action": event.get("action"),
                        "message": event.get("message"),
                        "classification": (event.get("details") or {}).get("classification"),
                    }
                )

        if healed_keys:
            aggregate.healed_keys_by_report[report_name] = healed_keys

    return aggregate


def _healed_ratio(aggregate: HealingAggregate) -> float:
    if aggregate.total_events == 0:
        return 0.0
    return aggregate.healed / aggregate.total_events


def _repeat_healed_keys(aggregate: HealingAggregate, threshold: int) -> list[str]:
    counts: dict[str, int] = {}
    for keys in aggregate.healed_keys_by_report.values():
        for key in keys:
            if key:
                counts[key] = counts.get(key, 0) + 1
    return [key for key, count in counts.items() if count >= threshold]


def run_ci_gates(
    *,
    workspace: Path,
    config: GateConfig,
    reports_dir: Path,
    tests_dir: Path,
    skip_queue_gates: bool = False,
) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if config.require_architecture_manifest:
        from healing.paths import MANIFEST_JSON
        from healing.architecture_scan import build_manifest

        if not MANIFEST_JSON.exists():
            errors.append(
                f"Architecture manifest missing: {MANIFEST_JSON}. "
                "Run: python -m healing.architecture_scan"
            )
        else:
            current = build_manifest(workspace)
            old = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
            if old.get("content_hash") != current.get("content_hash"):
                warnings.append(
                    "Architecture manifest is stale. Run: python -m healing.architecture_scan"
                )

    if not skip_queue_gates:
        from healing.healing_queue import list_awaiting_agent, list_patch_ready, list_unprocessed_failures

        unprocessed = len(list_unprocessed_failures())
        if unprocessed > config.max_unprocessed_failures:
            errors.append(
                f"Unprocessed failures ({unprocessed}) exceed max_unprocessed_failures "
                f"({config.max_unprocessed_failures}). Run healing-propose or review."
            )
        awaiting_agent = len(list_awaiting_agent())
        if awaiting_agent > config.max_awaiting_agent:
            warnings.append(
                f"Patches awaiting MCP agent ({awaiting_agent}) exceed soft limit "
                f"({config.max_awaiting_agent}). Run mcp_propose_runner or complete via Cursor."
            )
        patch_ready = len(list_patch_ready())
        if patch_ready > config.max_patch_ready_without_review:
            warnings.append(
                f"Patches awaiting review ({patch_ready}) exceed soft limit "
                f"({config.max_patch_ready_without_review}). Run /healing-review."
            )

    if config.test_policy_enabled:
        policy_errors, policy_warnings = check_test_policy(
            tests_dir=tests_dir,
            workspace=workspace,
            allowlist=[workspace / p for p in config.test_policy_allowlist],
            forbidden_patterns=config.test_policy_forbidden_patterns or None,
            require_pom_usage=config.require_pom_usage,
        )
        if config.test_policy_raw_mode == "allow":
            warnings.extend(policy_errors)
            warnings.extend(policy_warnings)
        elif config.test_policy_raw_mode == "warn":
            warnings.extend(policy_errors)
            warnings.extend(policy_warnings)
        else:
            errors.extend(policy_errors)
            warnings.extend(policy_warnings)

    aggregate = aggregate_healing_reports(reports_dir, config.ignore_report_globs)
    if aggregate.failed > config.max_failed_events:
        errors.append(
            f"Healing failed events ({aggregate.failed}) exceed max_failed_events "
            f"({config.max_failed_events})."
        )
        for item in aggregate.failed_events[:10]:
            errors.append(
                f"  - [{item['report']}] {item['key']} ({item['action']}): {item['message']}"
            )
        if len(aggregate.failed_events) > 10:
            errors.append(f"  - ... and {len(aggregate.failed_events) - 10} more")

    if aggregate.total_events >= config.min_events_for_ratio:
        ratio = _healed_ratio(aggregate)
        if ratio >= config.max_healed_ratio_fail:
            errors.append(
                f"Healed ratio {ratio:.2%} exceeds fail threshold "
                f"{config.max_healed_ratio_fail:.2%} "
                f"({aggregate.healed}/{aggregate.total_events} events)."
            )
        elif ratio >= config.max_healed_ratio_warn:
            warnings.append(
                f"Healed ratio {ratio:.2%} exceeds warn threshold "
                f"{config.max_healed_ratio_warn:.2%}."
            )

    repeat_keys = _repeat_healed_keys(aggregate, config.repeat_healed_key_warn)
    for key in repeat_keys:
        warnings.append(
            f"Semantic key '{key}' healed in {config.repeat_healed_key_warn}+ reports; "
            "consider promoting a stable locator via MCP/agent review."
        )

    exit_code = 1 if errors else 0
    return exit_code, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CI gates: test policy, architecture manifest, healing thresholds."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root.")
    parser.add_argument(
        "--config",
        default="healing/ci_gates_config.yaml",
        help="Gate config YAML path.",
    )
    parser.add_argument(
        "--reports-dir",
        default="healer-artifacts/healing-reports",
        help="Healing reports directory.",
    )
    parser.add_argument("--tests-dir", default="tests", help="Tests directory.")
    parser.add_argument(
        "--skip-reports",
        action="store_true",
        help="Skip healing report threshold checks (policy + queue only).",
    )
    parser.add_argument(
        "--skip-queue-gates",
        action="store_true",
        help="Skip healing-queue checks (unprocessed/awaiting_agent/patch_ready).",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    from healing.gates_config import load_healing_yaml

    config_path = workspace / args.config
    if config_path.exists():
        config = load_gate_config(config_path)
    else:
        config = gate_config_from_raw(load_healing_yaml(workspace))
        print(f"[healing] Using packaged gate config (no {config_path})")

    reports_dir = workspace / args.reports_dir

    if args.skip_reports:
        reports_dir = workspace / "healer-artifacts" / "healing-reports-nonexistent-skip"

    exit_code, errors, warnings = run_ci_gates(
        workspace=workspace,
        config=config,
        reports_dir=reports_dir,
        tests_dir=workspace / args.tests_dir,
        skip_queue_gates=args.skip_queue_gates,
    )

    print("=== CI Gates Summary ===")
    print(f"Reports dir: {workspace / args.reports_dir}")
    if not args.skip_reports:
        aggregate = aggregate_healing_reports(
            workspace / args.reports_dir, config.ignore_report_globs
        )
        print(
            f"Events: total={aggregate.total_events} primary={aggregate.primary} "
            f"healed={aggregate.healed} failed={aggregate.failed}"
        )

    if warnings:
        print("\nWARNINGS:")
        for item in warnings:
            print(f"- {item}")

    if errors:
        print("\nERRORS:")
        for item in errors:
            print(f"- {item}")
        print("\nCI gates FAILED.")
        return exit_code

    print("\nCI gates PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
