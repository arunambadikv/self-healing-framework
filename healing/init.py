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
# Automated MCP propose needs a provider + matching key.
# Failure capture, architecture scan, stub propose, review, and apply work without keys.

HEALING_LLM_PROVIDER=cursor
CURSOR_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
LITE_LLM_KEY=
# HEALING_LLM_MODEL=

# Opt-in: after healable locator failures, auto-run scan → stub → MCP propose
# (read from .env automatically — no need to export every time)
# HEALING_MCP_AUTO=1

# Persistent browser cache (recommended in Cursor — sandbox /tmp caches are ephemeral)
PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers
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
        from healing.mcp_constants import PLAYWRIGHT_MCP_PACKAGE

        dest.write_text(
            '{\n  "mcpServers": {\n    "playwright": {\n'
            '      "command": "npx",\n'
            f'      "args": ["{PLAYWRIGHT_MCP_PACKAGE}"]\n'
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


def _ensure_playwright_browsers(workspace: Path) -> str:
    dest = workspace / ".playwright-browsers"
    dest.mkdir(parents=True, exist_ok=True)
    gitignore = workspace / ".gitignore"
    marker = ".playwright-browsers/"
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        if ".playwright-browsers" not in text:
            gitignore.write_text(text.rstrip() + f"\n{marker}\n", encoding="utf-8")
    env_path = workspace / ".env"
    assignment = "PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers"
    if env_path.is_file():
        existing = env_path.read_text(encoding="utf-8")
        if "PLAYWRIGHT_BROWSERS_PATH" not in existing:
            env_path.write_text(existing.rstrip() + f"\n\n{assignment}\n", encoding="utf-8")
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
        "playwright_browsers": _ensure_playwright_browsers(workspace),
        "env_example": None,
        "skills": [],
        "scan": None,
    }
    from healing.package_sync import refresh_packaged_assets

    assets = refresh_packaged_assets(workspace, force=True)
    result["env_example"] = assets.get("env_example")
    result["skills"] = assets.get("skills") or []

    pages = workspace / "pages"
    if scan and pages.exists() and any(pages.glob("*.py")):
        from healing.auto_scan import run_auto_architecture_discovery

        scan_result = run_auto_architecture_discovery(workspace, force=True, quiet=True)
        result["scan"] = {
            "json": scan_result.get("json"),
            "md": scan_result.get("md"),
            "changed": scan_result.get("changed"),
            "content_hash": scan_result.get("content_hash"),
            "reason": scan_result.get("reason"),
            "package_version": scan_result.get("package_version"),
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
        help="With doctor: also run npx for the pinned @playwright/mcp package --help.",
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
        print(f"  wrote {result['env_example']} (copy to .env; set HEALING_LLM_PROVIDER + matching API key for MCP propose)")
    else:
        print("  .env.example already present")
    skills = result["skills"] or []
    if skills:
        print(f"  wrote {len(skills)} skill(s):")
        for path in skills:
            print(f"    - {path}")
    else:
        print("  skills refreshed from package templates")
    print("  healer-artifacts/ directories ensured")
    browsers = result.get("playwright_browsers")
    if browsers:
        print(f"  {browsers}/ ready — set PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers then playwright install chromium")
    print()
    print("Happy path:")
    print("  1. playwright install chromium")
    print("  2. cp .env.example .env  # set HEALING_LLM_PROVIDER + matching API key for MCP propose")
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
