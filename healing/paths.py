"""Artifact directory layout for POM healing pipeline (workspace-aware)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_workspace_override: Path | None = None


class DynamicPath:
    """Path-like value that always resolves against the current workspace + config."""

    def __init__(self, *parts: str) -> None:
        self._parts = parts

    def resolve_path(self) -> Path:
        from healing.config import get_config

        cfg = get_config()
        root = get_workspace()
        if self._parts and self._parts[0] == "artifacts":
            return root.joinpath(cfg.artifacts_dir, *self._parts[1:])
        return root.joinpath(*self._parts)

    def __truediv__(self, other: Any) -> Path:
        return self.resolve_path() / other

    def __fspath__(self) -> str:
        return os.fspath(self.resolve_path())

    def __str__(self) -> str:
        return str(self.resolve_path())

    def __repr__(self) -> str:
        return repr(self.resolve_path())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DynamicPath):
            return self.resolve_path() == other.resolve_path()
        if isinstance(other, (str, Path, os.PathLike)):
            return self.resolve_path() == Path(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.resolve_path())

    def __getattr__(self, name: str) -> Any:
        return getattr(self.resolve_path(), name)


def get_workspace() -> Path:
    if _workspace_override is not None:
        return _workspace_override
    env = os.environ.get("HEALING_WORKSPACE")
    if env:
        return Path(env).resolve()
    return Path.cwd()


def configure_workspace(root: Path | None = None) -> Path:
    """Pin artifact/layout resolution to an absolute workspace root."""
    global _workspace_override
    from healing.config import reset_config_cache

    reset_config_cache()
    if root is None:
        _workspace_override = get_workspace().resolve()
    else:
        _workspace_override = Path(root).resolve()
    os.environ["HEALING_WORKSPACE"] = str(_workspace_override)
    return _workspace_override


def reset_workspace() -> None:
    global _workspace_override
    from healing.config import reset_config_cache

    _workspace_override = None
    reset_config_cache()
    os.environ.pop("HEALING_WORKSPACE", None)


ARTIFACTS = DynamicPath("artifacts")
ARCHITECTURE_DIR = DynamicPath("artifacts", "architecture")
MANIFEST_JSON = DynamicPath("artifacts", "architecture", "manifest.json")
MANIFEST_MD = DynamicPath("artifacts", "architecture", "manifest.md")

FAILURES_DIR = DynamicPath("artifacts", "failures")
HEALING_QUEUE_DIR = DynamicPath("artifacts", "healing-queue")
QUEUE_INDEX = DynamicPath("artifacts", "healing-queue", "index.json")
QUEUE_PATCHES = DynamicPath("artifacts", "healing-queue", "patches")
QUEUE_APPLIED = DynamicPath("artifacts", "healing-queue", "applied")
QUEUE_SKIPPED = DynamicPath("artifacts", "healing-queue", "skipped")
QUEUE_SUMMARIES = DynamicPath("artifacts", "healing-queue", "summaries")
REPORTS_DIR = DynamicPath("artifacts", "healing-reports")
AUTH_DIR = DynamicPath("artifacts", "auth")


def ensure_queue_dirs() -> None:
    for path in (
        ARCHITECTURE_DIR,
        FAILURES_DIR,
        HEALING_QUEUE_DIR,
        QUEUE_PATCHES,
        QUEUE_APPLIED,
        QUEUE_SKIPPED,
        QUEUE_SUMMARIES,
        REPORTS_DIR,
        AUTH_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
