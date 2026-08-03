"""Initialize healing layout in a consumer Playwright POM project."""

from __future__ import annotations

import argparse
import shutil
from importlib import resources
from pathlib import Path

from healing.skill_paths import BUNDLED_SKILLS

DEFAULT_TOML = """\
pages_dir = "pages"
tests_dir = "tests"
data_dir = "data"
artifacts_dir = "healer-artifacts"
apply_roots = ["pages"]
skills_dir = ".cursor/skills"
mcp_config = ".cursor/mcp.json"
auth_dir = "healer-artifacts/auth"
"""

DEFAULT_ENV_EXAMPLE = """\
# Consumer secrets / toggles (copy to .env — never commit .env)
# Only CURSOR_API_KEY is required for automated MCP propose.
# Failure capture, architecture scan, stub propose, review, and apply work without it.

CURSOR_API_KEY=

# Opt-in: after healable locator failures, auto-run scan → stub → MCP propose
# (read from .env automatically — no need to export every time)
# HEALING_MCP_AUTO=1
"""

SKILL_NAMES = BUNDLED_SKILLS


def _templates_root() -> Path:
    try:
        root = resources.files("healing") / "templates"
        return Path(str(root))
    except Exception:
        return Path(__file__).resolve().parent / "templates"


def _copy_skill_templates(workspace: Path, *, force: bool = False) -> list[str]:
    written: list[str] = []
    templates = _templates_root() / "skills"
    skills_dir = workspace / ".cursor" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        src = templates / name / "SKILL.md"
        if not src.exists():
            continue
        dest_dir = skills_dir / name
        dest = dest_dir / "SKILL.md"
        if dest.exists() and not force:
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        written.append(str(dest.relative_to(workspace)))
    return written


def _write_mcp_stub(workspace: Path, *, force: bool = False) -> str | None:
    dest = workspace / ".cursor" / "mcp.json"
    if dest.exists() and not force:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = _templates_root() / "cursor" / "mcp.json"
    if src.exists():
        shutil.copy2(src, dest)
    else:
        dest.write_text(
            '{\n  "mcpServers": {\n    "playwright": {\n'
            '      "command": "npx",\n'
            '      "args": ["@playwright/mcp@latest"]\n'
            "    }\n  }\n}\n",
            encoding="utf-8",
        )
    return str(dest.relative_to(workspace))


def _write_healing_toml(workspace: Path, *, force: bool = False) -> str | None:
    dest = workspace / "healer-artifacts" / "healing.toml"
    if dest.exists() and not force:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = _templates_root() / "healer-artifacts" / "healing.toml"
    if src.exists():
        shutil.copy2(src, dest)
    else:
        dest.write_text(DEFAULT_TOML, encoding="utf-8")
    return str(dest.relative_to(workspace))


def _write_env_example(workspace: Path, *, force: bool = False) -> str | None:
    dest = workspace / ".env.example"
    if dest.exists() and not force:
        return None
    src = _templates_root() / "env.example"
    if src.exists():
        shutil.copy2(src, dest)
    else:
        dest.write_text(DEFAULT_ENV_EXAMPLE, encoding="utf-8")
    return str(dest.relative_to(workspace))


def init_workspace(
    workspace: Path,
    *,
    force: bool = False,
    scan: bool = True,
) -> dict[str, object]:
    from healing.paths import configure_workspace, ensure_queue_dirs

    workspace = configure_workspace(workspace.resolve())
    ensure_queue_dirs()

    result: dict[str, object] = {
        "workspace": str(workspace),
        "healing_toml": _write_healing_toml(workspace, force=force),
        "mcp": _write_mcp_stub(workspace, force=force),
        "env_example": _write_env_example(workspace, force=force),
        "skills": _copy_skill_templates(workspace, force=force),
        "scan": None,
    }

    pages = workspace / "pages"
    if scan and pages.exists() and any(pages.glob("*.py")):
        from healing.architecture_scan import build_manifest, write_manifest

        manifest = build_manifest(workspace)
        json_path, md_path, changed = write_manifest(manifest, workspace)
        result["scan"] = {
            "json": str(json_path),
            "md": str(md_path),
            "changed": changed,
            "content_hash": manifest.get("content_hash"),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize healing artifacts, config, and Cursor skills in a POM project."
    )
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument("--force", action="store_true", help="Overwrite existing skill/config files.")
    parser.add_argument("--no-scan", action="store_true", help="Skip initial architecture_scan.")
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="Skip healing-doctor after init.",
    )
    parser.add_argument(
        "--verify-mcp",
        action="store_true",
        help="With doctor: also run npx @playwright/mcp@latest --help.",
    )
    args = parser.parse_args()

    result = init_workspace(args.workspace, force=args.force, scan=not args.no_scan)
    print(f"[ok] Healing initialized in {result['workspace']}")
    if result["healing_toml"]:
        print(f"  wrote {result['healing_toml']}")
    else:
        print("  healer-artifacts/healing.toml already present")
    if result["mcp"]:
        print(f"  wrote {result['mcp']}")
    else:
        print("  .cursor/mcp.json already present")
    if result.get("env_example"):
        print(f"  wrote {result['env_example']} (copy to .env and set CURSOR_API_KEY for MCP propose)")
    else:
        print("  .env.example already present")
    skills = result["skills"] or []
    if skills:
        print(f"  wrote {len(skills)} skill(s):")
        for path in skills:
            print(f"    - {path}")
    else:
        print("  skills already present (use --force to refresh)")
    print("  healer-artifacts/ directories ensured")
    print()
    print("Happy path:")
    print("  1. playwright install chromium")
    print("  2. cp .env.example .env  # set CURSOR_API_KEY for MCP propose")
    print("  3. pytest tests/ -v")
    print("  4. optional: set HEALING_MCP_AUTO=1 in .env, then pytest tests/ -v")
    print("  healing-doctor          # re-check setup anytime")
    print("  Full guide: docs/CONSUMER_SETUP.md (in the healing package repo)")
    scan = result.get("scan")
    if isinstance(scan, dict):
        print(f"  architecture scan: hash={scan.get('content_hash')} changed={scan.get('changed')}")
    elif not args.no_scan:
        print("  architecture scan skipped (no pages/*.py yet)")

    if not args.no_check:
        print()
        from healing.doctor import format_report, run_doctor

        results = run_doctor(Path(str(result["workspace"])), verify_mcp=args.verify_mcp)
        print(format_report(results))
        if any(r.status == "error" for r in results):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
