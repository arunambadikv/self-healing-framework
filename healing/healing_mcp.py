"""Auto-generate MCP repair bundles after smart-test healing reports."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from healing.registry_updater import suggest_registry_updates


def _load_config(workspace: Path) -> dict[str, Any]:
    path = workspace / "healing" / "ci_gates_config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_healing_mcp_auto_enabled(*, workspace: Path | None = None) -> bool:
    """
    Whether to generate MCP bundles after each smart test healing report.

    Precedence: HEALING_MCP_AUTO env → legacy HEALING_TRIGGER_MCP_REPAIR=1 → config healing_mcp.auto_after_test (default true).
    """
    env = os.environ.get("HEALING_MCP_AUTO")
    if env is not None:
        return env.strip() not in ("0", "false", "no")
    if os.environ.get("HEALING_TRIGGER_MCP_REPAIR", "").strip() == "1":
        return True

    workspace = workspace or Path.cwd()
    config = _load_config(workspace)
    healing_mcp = config.get("healing_mcp", {})
    return bool(healing_mcp.get("auto_after_test", True))


def is_raw_mcp_enabled(*, workspace: Path | None = None) -> bool:
    """Whether raw-learning runs should generate MCP bundles (HEALING_RAW_MCP env overrides config)."""
    env = os.environ.get("HEALING_RAW_MCP")
    if env is not None:
        return env.strip() not in ("0", "false", "no")
    workspace = workspace or Path.cwd()
    config = _load_config(workspace)
    return bool(config.get("raw_learning", {}).get("mcp_bundles", True))


def should_generate_mcp_for_report(report_path: Path, summary: dict[str, Any]) -> bool:
    """True when the report has healing events or patch suggestions worth MCP review."""
    if summary.get("healed", 0) > 0 or summary.get("failed", 0) > 0:
        return True
    return bool(suggest_registry_updates(report_path))


def finalize_healing_mcp(
    *,
    report_path: Path,
    base_url: str,
    summary: dict[str, Any],
    workspace: Path | None = None,
) -> int:
    """
    Generate MCP repair prompts/plans for a smart-test healing report.
    Returns number of bundles written (0 if skipped or no triggers).
    """
    workspace = workspace or Path.cwd()
    if not is_healing_mcp_auto_enabled(workspace=workspace):
        return 0
    if not should_generate_mcp_for_report(report_path, summary):
        return 0

    from healing.mcp_repair_pipeline import generate_bundles_for_report

    config = _load_config(workspace)
    mcp_cfg = config.get("mcp_repair", {})
    output_dir = workspace / mcp_cfg.get("output_dir", "artifacts/mcp-repair-bundles")

    return generate_bundles_for_report(
        report_path,
        registry_path=workspace / "locator_registry.yaml",
        output_dir=output_dir,
        base_url=base_url or mcp_cfg.get("default_base_url", "https://seleniumbase.io/demo_page"),
    )
