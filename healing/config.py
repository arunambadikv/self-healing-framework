"""Project configuration for the healing package."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]


@dataclass
class HealingConfig:
    pages_dir: str = "pages"
    tests_dir: str = "tests"
    data_dir: str = "data"
    artifacts_dir: str = "healer-artifacts"
    apply_roots: list[str] = field(default_factory=lambda: ["pages"])
    skills_dir: str = ".cursor/skills"
    mcp_config: str = ".cursor/mcp.json"
    auth_dir: str = "healer-artifacts/auth"


_config_cache: HealingConfig | None = None
_config_workspace: Path | None = None


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as fh:
        return tomllib.loads(fh.read().decode("utf-8"))


def _config_toml_candidates(root: Path) -> list[Path]:
    """Canonical healer-artifacts/healing.toml, then legacy paths for compat."""
    return [
        root / "healer-artifacts" / "healing.toml",
        root / "healer" / "healing.toml",
        root / "healing.toml",
    ]


def load_config(workspace: Path | None = None) -> HealingConfig:
    """Load healer-artifacts/healing.toml, legacy paths, or [tool.healing] from pyproject.toml."""
    global _config_cache, _config_workspace
    root = (workspace or Path(os.environ.get("HEALING_WORKSPACE", Path.cwd()))).resolve()
    if _config_cache is not None and _config_workspace == root:
        return _config_cache

    data: dict[str, Any] = {}
    for healing_toml in _config_toml_candidates(root):
        if healing_toml.exists():
            raw = _load_toml(healing_toml)
            data = raw.get("healing", raw) if isinstance(raw, dict) else {}
            break
    else:
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            raw = _load_toml(pyproject)
            tool = raw.get("tool") or {}
            data = tool.get("healing") or {}

    cfg = HealingConfig(
        pages_dir=str(data.get("pages_dir", "pages")),
        tests_dir=str(data.get("tests_dir", "tests")),
        data_dir=str(data.get("data_dir", "data")),
        artifacts_dir=str(data.get("artifacts_dir", "healer-artifacts")),
        apply_roots=list(data.get("apply_roots") or ["pages"]),
        skills_dir=str(data.get("skills_dir", ".cursor/skills")),
        mcp_config=str(data.get("mcp_config", ".cursor/mcp.json")),
        auth_dir=str(data.get("auth_dir", "healer-artifacts/auth")),
    )
    _config_cache = cfg
    _config_workspace = root
    return cfg


def get_config() -> HealingConfig:
    from healing.paths import get_workspace

    return load_config(get_workspace())


def reset_config_cache() -> None:
    global _config_cache, _config_workspace
    _config_cache = None
    _config_workspace = None
