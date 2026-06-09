"""Post-pytest healing chain (architecture scan, propose, MCP runner)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from healing.paths import MANIFEST_JSON


def _python() -> str:
    return sys.executable


def _load_healing_config(workspace: Path) -> dict[str, Any]:
    config_path = workspace / "healing" / "ci_gates_config.yaml"
    if not config_path.exists():
        return {}
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def is_auto_enabled(workspace: Path | None = None) -> bool:
    if os.environ.get("HEALING_MCP_AUTO", "").strip() in ("1", "true", "yes"):
        return True
    workspace = workspace or Path.cwd()
    config = _load_healing_config(workspace)
    return bool(config.get("healing_mcp", {}).get("auto_after_test", False))


def manifest_is_stale(workspace: Path) -> bool:
    from healing.architecture_scan import build_manifest

    manifest_path = workspace / MANIFEST_JSON
    if not manifest_path.exists():
        return True
    try:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        current = build_manifest(workspace)
        return old.get("content_hash") != current.get("content_hash")
    except Exception:
        return True


def run_architecture_scan_if_needed(workspace: Path) -> None:
    if not manifest_is_stale(workspace):
        return
    subprocess.run(
        [_python(), "-m", "healing.architecture_scan", "--workspace", str(workspace)],
        cwd=workspace,
        check=False,
    )


def run_pom_propose_all(workspace: Path) -> None:
    subprocess.run(
        [_python(), "-m", "healing.pom_propose", "--process-all", "--workspace", str(workspace)],
        cwd=workspace,
        check=False,
    )


def run_mcp_propose_all(workspace: Path) -> None:
    subprocess.run(
        [_python(), "-m", "healing.mcp_propose_runner", "--process-all", "--workspace", str(workspace)],
        cwd=workspace,
        check=False,
    )


def should_run_post_test_chain(workspace: Path | None = None) -> bool:
    """True when auto is enabled and this session captured healable locator failures."""
    workspace = (workspace or Path.cwd()).resolve()
    if not is_auto_enabled(workspace):
        return False
    from healing.session_state import session_had_healable_failures

    return session_had_healable_failures()


def run_post_test_chain(workspace: Path | None = None) -> None:
    """Run optional post-test healing steps when HEALING_MCP_AUTO=1 or config flag set."""
    workspace = (workspace or Path.cwd()).resolve()
    if not is_auto_enabled(workspace):
        return
    if not should_run_post_test_chain(workspace):
        print(
            "\n[healing] HEALING_MCP_AUTO enabled — skipping post-test chain "
            "(no healable locator failures captured this session)"
        )
        return
    print("\n[healing] HEALING_MCP_AUTO enabled — running post-test chain")
    run_architecture_scan_if_needed(workspace)
    run_pom_propose_all(workspace)
    run_mcp_propose_all(workspace)
