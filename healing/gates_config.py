"""Load healing gate / MCP YAML config from workspace or packaged defaults."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml


def load_healing_yaml(workspace: Path | None = None) -> dict[str, Any]:
    """Load ci_gates_config.yaml: workspace override, else packaged defaults.

    Search order:
    1. ``{workspace}/healing/ci_gates_config.yaml``
    2. Package data ``healing/ci_gates_config.yaml`` via importlib.resources
    """
    root = (workspace or Path.cwd()).resolve()
    override = root / "healing" / "ci_gates_config.yaml"
    if override.is_file():
        return yaml.safe_load(override.read_text(encoding="utf-8")) or {}

    try:
        pkg = resources.files("healing")
        packaged = pkg.joinpath("ci_gates_config.yaml")
        if packaged.is_file():
            return yaml.safe_load(packaged.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, TypeError, AttributeError):
        pass

    # Editable-install fallback next to this module
    sibling = Path(__file__).resolve().parent / "ci_gates_config.yaml"
    if sibling.is_file():
        return yaml.safe_load(sibling.read_text(encoding="utf-8")) or {}
    return {}
