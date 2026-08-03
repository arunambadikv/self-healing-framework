"""Readable artifact ID naming: F-{test}-{stamp} / P-{test}-{stamp}."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")
_MULTI_DASH = re.compile(r"-{2,}")
_MAX_SLUG = 48


def slugify_test_name(name: str | None) -> str:
    """Normalize a pytest test name / nodeid into a filesystem-safe slug."""
    raw = (name or "").strip()
    if "::" in raw:
        raw = raw.rsplit("::", 1)[-1]
    raw = raw.replace("[", "-").replace("]", "")
    slug = _UNSAFE.sub("-", raw)
    slug = _MULTI_DASH.sub("-", slug).strip("-_")
    if not slug:
        return "unknown"
    if len(slug) > _MAX_SLUG:
        slug = slug[:_MAX_SLUG].rstrip("-_")
    return slug or "unknown"


def utc_stamp() -> str:
    """UTC timestamp at second precision: YYYYMMDD-HHMMSS."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _id_taken(directory: Path, artifact_id: str, suffixes: tuple[str, ...]) -> bool:
    for suffix in suffixes:
        if (directory / f"{artifact_id}{suffix}").exists():
            return True
    return False


def build_artifact_id(
    prefix: str,
    test_name: str | None,
    *,
    directory: Path,
    suffixes: tuple[str, ...] = (".json", ".md"),
    stamp: str | None = None,
) -> str:
    """
    Build ``{prefix}-{slug}-{stamp}``, appending ``-2``, ``-3``, … when taken.

    ``directory`` is probed for any of ``suffixes`` so JSON/MD/agent-task collide safely.
    """
    slug = slugify_test_name(test_name)
    base_stamp = stamp or utc_stamp()
    candidate = f"{prefix}-{slug}-{base_stamp}"
    if not _id_taken(directory, candidate, suffixes):
        return candidate
    n = 2
    while True:
        candidate = f"{prefix}-{slug}-{base_stamp}-{n}"
        if not _id_taken(directory, candidate, suffixes):
            return candidate
        n += 1
