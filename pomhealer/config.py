"""Project configuration for the pomhealer package."""

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
class PomhealerConfig:
    pages_dir: str = "pages"
    tests_dir: str = "tests"
    data_dir: str = "data"
    artifacts_dir: str = "pomhealer-artifacts"
    apply_roots: list[str] = field(default_factory=lambda: ["pages"])
    skills_dir: str = ".cursor/skills"
    mcp_config: str = ".cursor/mcp.json"
    auth_dir: str = "pomhealer-artifacts/auth"


_config_cache: PomhealerConfig | None = None
_config_workspace: Path | None = None


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as fh:
        return tomllib.loads(fh.read().decode("utf-8"))


def _config_toml_candidates(root: Path) -> list[Path]:
    """Canonical pomhealer-artifacts/pomhealer.toml only."""
    return [
        root / "pomhealer-artifacts" / "pomhealer.toml",
    ]


def load_config(workspace: Path | None = None) -> PomhealerConfig:
    """Load pomhealer-artifacts/pomhealer.toml, legacy paths, or [tool.pomhealer] from pyproject.toml."""
    global _config_cache, _config_workspace
    root = (workspace or Path(os.environ.get("POMHEALER_WORKSPACE", Path.cwd()))).resolve()
    if _config_cache is not None and _config_workspace == root:
        return _config_cache

    data: dict[str, Any] = {}
    for healing_toml in _config_toml_candidates(root):
        if healing_toml.exists():
            raw = _load_toml(healing_toml)
            data = raw.get("pomhealer", raw) if isinstance(raw, dict) else {}
            break
    else:
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            raw = _load_toml(pyproject)
            tool = raw.get("tool") or {}
            data = tool.get("pomhealer") or {}

    cfg = PomhealerConfig(
        pages_dir=str(data.get("pages_dir", "pages")),
        tests_dir=str(data.get("tests_dir", "tests")),
        data_dir=str(data.get("data_dir", "data")),
        artifacts_dir=str(data.get("artifacts_dir", "pomhealer-artifacts")),
        apply_roots=list(data.get("apply_roots") or ["pages"]),
        skills_dir=str(data.get("skills_dir", ".cursor/skills")),
        mcp_config=str(data.get("mcp_config", ".cursor/mcp.json")),
        auth_dir=str(data.get("auth_dir", "pomhealer-artifacts/auth")),
    )
    _config_cache = cfg
    _config_workspace = root
    return cfg


def get_config() -> PomhealerConfig:
    from pomhealer.paths import get_workspace

    return load_config(get_workspace())


def reset_config_cache() -> None:
    global _config_cache, _config_workspace
    _config_cache = None
    _config_workspace = None
