"""Finalize raw test runs: healing reports, registry drafts, MCP bundles."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from healing.raw_recorder import RawObservation, RawObservationCollector
from healing.healing_mcp import is_raw_mcp_enabled


def observations_to_healing_report(collector: RawObservationCollector) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for obs in collector.observations:
        events.append(
            {
                "key": obs.semantic_key,
                "action": obs.action,
                "status": "primary",
                "used_candidate": obs.candidate,
                "message": "Captured from raw Playwright test (auto-learning).",
                "details": {
                    "classification": "add_semantic_key",
                    "source": "raw_learning",
                    "test_name": obs.test_name,
                    "suggested_registry_entry": registry_entry_from_observation(obs),
                },
            }
        )
    summary = {"total": len(events), "primary": len(events), "healed": 0, "failed": 0}
    return {"events": events, "summary": summary}


def registry_entry_from_observation(obs: RawObservation) -> dict[str, Any]:
    return {
        "intent": obs.intent,
        "action": obs.action,
        "preferred": [obs.candidate],
        "fallback": [],
    }


def observations_to_registry_map(observations: list[RawObservation]) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    for obs in observations:
        registry[obs.semantic_key] = registry_entry_from_observation(obs)
    return registry


def merge_registry_draft(
    *,
    registry_path: Path,
    observations: list[RawObservation],
    apply: bool,
) -> list[str]:
    """Add auto.* keys that are not already present. Returns keys added."""
    if not observations:
        return []

    existing: dict[str, Any] = {}
    if registry_path.exists():
        loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            existing = loaded

    added: list[str] = []
    for obs in observations:
        if obs.semantic_key in existing:
            continue
        existing[obs.semantic_key] = registry_entry_from_observation(obs)
        added.append(obs.semantic_key)

    if apply and added:
        registry_path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")

    return added


def finalize_raw_learning(
    *,
    collector: RawObservationCollector,
    test_name: str,
    base_url: str,
    workspace: Path | None = None,
) -> dict[str, Any]:
    workspace = workspace or Path.cwd()
    output_dir = workspace / "artifacts" / "raw-learning"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = observations_to_healing_report(collector)
    report_path = output_dir / "reports" / f"{test_name}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    draft_registry = observations_to_registry_map(collector.observations)
    draft_path = output_dir / "registry-drafts" / f"{test_name}.yaml"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(yaml.safe_dump(draft_registry, sort_keys=False), encoding="utf-8")

    registry_path = workspace / "locator_registry.yaml"
    auto_apply = os.environ.get("HEALING_REGISTRY_AUTO_APPLY", "").strip() in ("1", "true", "yes")
    added_keys = merge_registry_draft(
        registry_path=registry_path,
        observations=collector.observations,
        apply=auto_apply,
    )

    mcp_count = 0
    if is_raw_mcp_enabled(workspace=workspace) and report.get("events"):
        from healing.mcp_repair_pipeline import generate_bundles_for_report

        mcp_count = generate_bundles_for_report(
            report_path,
            registry_path=registry_path,
            output_dir=workspace / "artifacts" / "mcp-repair-bundles",
            base_url=base_url,
        )

    return {
        "report_path": str(report_path),
        "draft_path": str(draft_path),
        "observation_count": len(collector.observations),
        "registry_keys_added": added_keys,
        "registry_auto_applied": auto_apply,
        "mcp_bundles": mcp_count,
    }
