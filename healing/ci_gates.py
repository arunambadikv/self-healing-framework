from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from healing.registry import lint_registry, validate_registry
from healing.test_policy import check_test_policy


@dataclass
class GateConfig:
    ignore_report_globs: list[str] = field(default_factory=list)
    max_failed_events: int = 0
    max_healed_ratio_warn: float = 0.10
    max_healed_ratio_fail: float = 0.30
    min_events_for_ratio: int = 1
    repeat_healed_key_warn: int = 2
    registry_lint_enabled: bool = True
    registry_fail_on_warnings: bool = False
    test_policy_enabled: bool = True
    test_policy_allowlist: list[str] = field(default_factory=list)
    test_policy_forbidden_patterns: list[str] = field(default_factory=list)
    require_smart_fixture: bool = True
    test_policy_raw_mode: str = "allow"


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
    thresholds = raw.get("thresholds", {})
    registry = raw.get("registry_lint", {})
    policy = raw.get("test_policy", {})
    return GateConfig(
        ignore_report_globs=list(thresholds.get("ignore_report_globs", [])),
        max_failed_events=int(thresholds.get("max_failed_events", 0)),
        max_healed_ratio_warn=float(thresholds.get("max_healed_ratio_warn", 0.10)),
        max_healed_ratio_fail=float(thresholds.get("max_healed_ratio_fail", 0.30)),
        min_events_for_ratio=int(thresholds.get("min_events_for_ratio", 1)),
        repeat_healed_key_warn=int(thresholds.get("repeat_healed_key_warn", 2)),
        registry_lint_enabled=bool(registry.get("enabled", True)),
        registry_fail_on_warnings=bool(registry.get("fail_on_warnings", False)),
        test_policy_enabled=bool(policy.get("enabled", True)),
        test_policy_allowlist=list(policy.get("allowlist", [])),
        test_policy_forbidden_patterns=list(policy.get("forbidden_patterns", [])),
        require_smart_fixture=bool(policy.get("require_smart_fixture", True)),
        test_policy_raw_mode=str(policy.get("raw_mode", "allow")),
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
    registry_path: Path,
    tests_dir: Path,
) -> tuple[int, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if config.registry_lint_enabled:
        if not registry_path.exists():
            errors.append(f"Registry not found: {registry_path}")
        else:
            import yaml as yaml_lib

            registry = yaml_lib.safe_load(registry_path.read_text(encoding="utf-8"))
            validation_errors = validate_registry(registry)
            lint_warnings = lint_registry(registry) if isinstance(registry, dict) else []
            errors.extend(validation_errors)
            if config.registry_fail_on_warnings:
                errors.extend(lint_warnings)
            else:
                warnings.extend(lint_warnings)

    if config.test_policy_enabled:
        policy_errors, policy_warnings = check_test_policy(
            tests_dir=tests_dir,
            workspace=workspace,
            allowlist=[workspace / p for p in config.test_policy_allowlist],
            forbidden_patterns=config.test_policy_forbidden_patterns or None,
            require_smart_fixture=config.require_smart_fixture,
        )
        if config.test_policy_raw_mode == "allow":
            warnings.extend(policy_errors)
            warnings.extend(policy_warnings)
        elif config.test_policy_raw_mode == "warn":
            warnings.extend(policy_errors)
            warnings.extend(policy_warnings)
            errors.extend([e for e in policy_errors if "missing `smart` fixture" in e])
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
            "consider registry promotion via MCP/agent review."
        )

    exit_code = 1 if errors else 0
    return exit_code, errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Phase A CI gates: registry lint, smart test policy, healing thresholds."
    )
    parser.add_argument("--workspace", default=".", help="Workspace root.")
    parser.add_argument(
        "--config",
        default="healing/ci_gates_config.yaml",
        help="Gate config YAML path.",
    )
    parser.add_argument(
        "--reports-dir",
        default="artifacts/healing-reports",
        help="Healing reports directory.",
    )
    parser.add_argument(
        "--registry",
        default="locator_registry.yaml",
        help="Locator registry path.",
    )
    parser.add_argument("--tests-dir", default="tests", help="Tests directory.")
    parser.add_argument(
        "--skip-reports",
        action="store_true",
        help="Skip healing report threshold checks (registry + policy only).",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    config_path = workspace / args.config
    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}")
        return 2

    config = load_gate_config(config_path)
    reports_dir = workspace / args.reports_dir

    if args.skip_reports:
        reports_dir = workspace / "artifacts" / "healing-reports-nonexistent-skip"

    exit_code, errors, warnings = run_ci_gates(
        workspace=workspace,
        config=config,
        reports_dir=reports_dir,
        registry_path=workspace / args.registry,
        tests_dir=workspace / args.tests_dir,
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
