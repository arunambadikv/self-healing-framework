"""Artifact directory layout for POM healing pipeline."""

from __future__ import annotations

from pathlib import Path

ARTIFACTS = Path("artifacts")
ARCHITECTURE_DIR = ARTIFACTS / "architecture"
MANIFEST_JSON = ARCHITECTURE_DIR / "manifest.json"
MANIFEST_MD = ARCHITECTURE_DIR / "manifest.md"

FAILURES_DIR = ARTIFACTS / "failures"
HEALING_QUEUE_DIR = ARTIFACTS / "healing-queue"
QUEUE_INDEX = HEALING_QUEUE_DIR / "index.json"
QUEUE_PATCHES = HEALING_QUEUE_DIR / "patches"
QUEUE_APPLIED = HEALING_QUEUE_DIR / "applied"
QUEUE_SKIPPED = HEALING_QUEUE_DIR / "skipped"
QUEUE_SUMMARIES = HEALING_QUEUE_DIR / "summaries"


def ensure_queue_dirs() -> None:
    for path in (
        ARCHITECTURE_DIR,
        FAILURES_DIR,
        HEALING_QUEUE_DIR,
        QUEUE_PATCHES,
        QUEUE_APPLIED,
        QUEUE_SKIPPED,
        QUEUE_SUMMARIES,
    ):
        path.mkdir(parents=True, exist_ok=True)
