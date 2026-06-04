"""Canonical Cursor skill paths."""

from __future__ import annotations

from pathlib import Path

SKILLS_ROOT = Path(".cursor/skills")

SKILL_FILE_MAP = {
    "playwright-locator-repair": SKILLS_ROOT / "playwright-locator-repair" / "SKILL.md",
    "architecture-discovery": SKILLS_ROOT / "architecture-discovery" / "SKILL.md",
    "healing-propose": SKILLS_ROOT / "healing-propose" / "SKILL.md",
    "healing-review": SKILLS_ROOT / "healing-review" / "SKILL.md",
}


def load_skill_text(name: str) -> str:
    path = SKILL_FILE_MAP.get(name)
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    return f"# Missing skill file: {path or name}"
