"""Refresh packaged skills / env.example / MCP pin after pip install from git."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from healing.mcp_constants import PLAYWRIGHT_MCP_PACKAGE
from healing.paths import ARCHITECTURE_DIR, ensure_queue_dirs
from healing.skill_paths import BUNDLED_SKILLS


def assets_fingerprint_path() -> Path:
    return Path(str(ARCHITECTURE_DIR)) / ".healing-assets-fingerprint"


def packaged_assets_fingerprint() -> str:
    """Hash of templates consumers should receive on package update."""
    from healing.init import _templates_root

    digest = hashlib.sha256()
    root = _templates_root()
    rels = ["env.example", "cursor/mcp.json"]
    for name in BUNDLED_SKILLS:
        rels.append(f"skills/{name}/SKILL.md")
    for rel in rels:
        path = root / rel
        digest.update(rel.encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    digest.update(PLAYWRIGHT_MCP_PACKAGE.encode("utf-8"))
    return digest.hexdigest()[:16]


def read_assets_fingerprint() -> str | None:
    path = assets_fingerprint_path()
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def mark_packaged_assets_current() -> Path:
    ensure_queue_dirs()
    path = assets_fingerprint_path()
    path.write_text(packaged_assets_fingerprint() + "\n", encoding="utf-8")
    return path


def pin_playwright_mcp_config(workspace: Path) -> bool:
    """Point existing .cursor/mcp.json Playwright server at the packaged pin."""
    path = workspace / ".cursor" / "mcp.json"
    if not path.is_file():
        from healing.init import _write_mcp_stub

        return bool(_write_mcp_stub(workspace, force=False))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return False
    playwright = servers.get("playwright")
    if not isinstance(playwright, dict):
        return False
    args = list(playwright.get("args") or [])
    changed = False
    new_args: list[Any] = []
    saw_pkg = False
    for arg in args:
        if isinstance(arg, str) and arg.startswith("@playwright/mcp"):
            saw_pkg = True
            if arg != PLAYWRIGHT_MCP_PACKAGE:
                changed = True
            new_args.append(PLAYWRIGHT_MCP_PACKAGE)
        else:
            new_args.append(arg)
    if not saw_pkg or not changed:
        return False
    playwright["args"] = new_args
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def refresh_packaged_assets(workspace: Path, *, force: bool = False) -> dict[str, Any]:
    """Copy bundled skills and .env.example; pin Playwright MCP.

    Does not overwrite healer-artifacts/healing.toml or consumer .env.
    Bundled Cursor skills are owned by the package.
    """
    from healing.init import _copy_skill_templates, _write_env_example
    from healing.paths import configure_workspace

    workspace = configure_workspace(workspace.resolve())
    fp = packaged_assets_fingerprint()
    if not force and read_assets_fingerprint() == fp:
        return {"refreshed": False, "reason": "packaged assets up to date", "skills": [], "env_example": None}

    skills = _copy_skill_templates(workspace, force=True)
    env_example = _write_env_example(workspace, force=True)
    mcp_pinned = pin_playwright_mcp_config(workspace)
    mark_packaged_assets_current()
    result = {
        "refreshed": True,
        "reason": "package templates changed" if not force else "forced",
        "skills": skills,
        "env_example": env_example,
        "mcp_pinned": mcp_pinned,
        "fingerprint": fp,
    }
    return result


def refresh_packaged_assets_if_stale(workspace: Path, *, quiet: bool = False) -> dict[str, Any]:
    """No-op when fingerprint matches; used after pip install from git."""
    result = refresh_packaged_assets(workspace, force=False)
    if result.get("refreshed") and not quiet:
        skills = result.get("skills") or []
        parts = [f"{len(skills)} skill(s)"]
        if result.get("env_example"):
            parts.append(".env.example")
        if result.get("mcp_pinned"):
            parts.append("mcp.json pin")
        print("[healing] refreshed packaged assets after install/update: " + ", ".join(parts))
        print("[healing] merge any new keys from .env.example into .env (do not commit .env)")
    return result
