"""Canonical Cursor skill paths with package-template fallback."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

# Consumer needs HEALING_LLM_PROVIDER + matching API key for automated MCP propose.
# push-to-dev is intentionally omitted — it encodes this repo's git policy.
BUNDLED_SKILLS = (
    "architecture-discovery",
    "healing-init",
    "healing-propose",
    "healing-review",
    "playwright-locator-repair",
)

# Workspace-only skills (not bundled); still loadable when present under skills_dir.
WORKSPACE_ONLY_SKILLS = ("push-to-dev",)


def _templates_skills_root() -> Path:
    try:
        root = resources.files("healing") / "templates" / "skills"
        return Path(str(root))
    except Exception:
        return Path(__file__).resolve().parent / "templates" / "skills"


def workspace_skills_dir() -> Path:
    from healing.config import get_config
    from healing.paths import get_workspace

    cfg = get_config()
    return get_workspace() / cfg.skills_dir


def resolve_skill_path(name: str) -> Path | None:
    """Return the best available SKILL.md path (workspace first, then package)."""
    ws = workspace_skills_dir() / name / "SKILL.md"
    if ws.exists():
        return ws
    if name in BUNDLED_SKILLS:
        bundled = _templates_skills_root() / name / "SKILL.md"
        if bundled.exists():
            return bundled
    return None


def load_skill_text(name: str) -> str:
    path = resolve_skill_path(name)
    if path is not None and path.exists():
        return path.read_text(encoding="utf-8")
    return f"# Missing skill file: {name} (not in workspace skills_dir or package templates)"


# Backward-compatible map for callers that inspect paths (workspace-relative).
SKILLS_ROOT = Path(".cursor/skills")
SKILL_FILE_MAP = {
    name: SKILLS_ROOT / name / "SKILL.md"
    for name in (*BUNDLED_SKILLS, *WORKSPACE_ONLY_SKILLS)
}
