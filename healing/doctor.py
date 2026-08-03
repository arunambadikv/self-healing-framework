"""Consumer environment checks (`healing-doctor`)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # ok | warn | error
    detail: str


def load_dotenv_files(workspace: Path) -> list[Path]:
    """Load workspace .env into os.environ (does not override existing vars)."""
    loaded: list[Path] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded
    for name in (".env", ".env.local"):
        path = workspace / name
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(path)
    return loaded


def _check_package_import() -> CheckResult:
    try:
        import healing  # noqa: F401

        loc = getattr(healing, "__file__", None) or "(namespace)"
        return CheckResult("healing package", "ok", f"importable ({loc})")
    except Exception as exc:
        return CheckResult("healing package", "error", f"import failed: {exc}")


def _check_pytest_plugin() -> CheckResult:
    try:
        eps = metadata.entry_points()
        selected = eps.select(group="pytest11") if hasattr(eps, "select") else eps.get("pytest11", [])
        names = {ep.name: ep.value for ep in selected}
        if "healing" in names:
            return CheckResult("pytest plugin", "ok", f"pytest11 entry healing → {names['healing']}")
        return CheckResult(
            "pytest plugin",
            "warn",
            "pytest11 entry 'healing' not found (reinstall package or add -p healing.pytest_plugin)",
        )
    except Exception as exc:
        return CheckResult("pytest plugin", "warn", f"could not inspect entry points: {exc}")


def _check_cursor_sdk() -> CheckResult:
    try:
        import cursor_sdk  # noqa: F401

        return CheckResult("cursor-sdk", "ok", "installed (MCP propose ready)")
    except ImportError:
        return CheckResult(
            "cursor-sdk",
            "warn",
            "not installed — pip install 'healing[mcp]' for automated MCP propose",
        )


def _check_playwright_browsers() -> CheckResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return CheckResult("playwright", "error", "playwright not installed")
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and Path(path).exists():
                return CheckResult("chromium", "ok", f"executable at {path}")
            return CheckResult(
                "chromium",
                "warn",
                "chromium executable missing — run: playwright install chromium",
            )
    except Exception as exc:
        return CheckResult(
            "chromium",
            "warn",
            f"could not resolve chromium ({exc}) — run: playwright install chromium",
        )


def _check_npx() -> CheckResult:
    npx = shutil.which("npx")
    if not npx:
        return CheckResult(
            "npx (Node)",
            "warn",
            "npx not found — install Node.js 18+ for Playwright MCP propose",
        )
    try:
        proc = subprocess.run(
            [npx, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        ver = (proc.stdout or proc.stderr or "").strip().splitlines()[0] if proc.returncode == 0 else "unknown"
        return CheckResult("npx (Node)", "ok", f"{npx} ({ver})")
    except Exception as exc:
        return CheckResult("npx (Node)", "warn", f"npx present but failed: {exc}")


def _check_mcp_json(workspace: Path) -> CheckResult:
    path = workspace / ".cursor" / "mcp.json"
    if not path.exists():
        return CheckResult(
            "mcp.json",
            "warn",
            "missing .cursor/mcp.json — run healing-init (CLI propose still has built-in defaults)",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") or {}
        if "playwright" in servers or any("playwright" in k for k in servers):
            return CheckResult("mcp.json", "ok", str(path.relative_to(workspace)))
        return CheckResult("mcp.json", "warn", f"{path.name} has no playwright server entry")
    except Exception as exc:
        return CheckResult("mcp.json", "warn", f"unreadable: {exc}")


def _check_api_key(workspace: Path) -> CheckResult:
    load_dotenv_files(workspace)
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if key:
        return CheckResult("CURSOR_API_KEY", "ok", "set (env or .env)")
    env_example = workspace / ".env.example"
    hint = "set CURSOR_API_KEY for automated MCP propose (capture/review work without it)"
    if env_example.exists():
        hint += f" — see {env_example.name}"
    return CheckResult("CURSOR_API_KEY", "warn", hint)


def _check_config(workspace: Path) -> CheckResult:
    candidates = [
        workspace / "healer-artifacts" / "healing.toml",
        workspace / "healer" / "healing.toml",
        workspace / "healing.toml",
    ]
    for path in candidates:
        if path.exists():
            return CheckResult("healing.toml", "ok", str(path.relative_to(workspace)))
    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        if "[tool.healing]" in text:
            return CheckResult("healing.toml", "ok", "using [tool.healing] in pyproject.toml")
    return CheckResult(
        "healing.toml",
        "warn",
        "no healer-artifacts/healing.toml — run healing-init (defaults still apply)",
    )


def _check_artifact_dirs(workspace: Path) -> CheckResult:
    from healing.config import load_config
    from healing.paths import configure_workspace, FAILURES_DIR

    configure_workspace(workspace)
    cfg = load_config(workspace)
    failures = Path(str(FAILURES_DIR))
    if failures.is_dir():
        return CheckResult("artifact dirs", "ok", f"{cfg.artifacts_dir}/ (failures present)")
    return CheckResult(
        "artifact dirs",
        "warn",
        f"{cfg.artifacts_dir}/ not initialized — run healing-init",
    )


def _check_skills(workspace: Path) -> CheckResult:
    from healing.skill_paths import BUNDLED_SKILLS, resolve_skill_path

    missing = [n for n in BUNDLED_SKILLS if resolve_skill_path(n) is None]
    if missing:
        return CheckResult("skills", "warn", f"missing: {', '.join(missing)}")
    ws = workspace / ".cursor" / "skills"
    where = "workspace .cursor/skills" if ws.exists() else "package templates"
    return CheckResult("skills", "ok", f"{len(BUNDLED_SKILLS)} skills via {where}")


def verify_playwright_mcp(*, timeout_sec: float = 60.0) -> CheckResult:
    """Optional live check: npx can resolve @playwright/mcp."""
    npx = shutil.which("npx")
    if not npx:
        return CheckResult("playwright MCP", "warn", "skipped — npx not available")
    try:
        proc = subprocess.run(
            [npx, "--yes", "@playwright/mcp@latest", "--help"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode == 0:
            return CheckResult("playwright MCP", "ok", "npx @playwright/mcp@latest responded")
        err = (proc.stderr or proc.stdout or "").strip()[:200]
        return CheckResult("playwright MCP", "warn", f"npx mcp help failed: {err or proc.returncode}")
    except subprocess.TimeoutExpired:
        return CheckResult("playwright MCP", "warn", f"timed out after {timeout_sec}s")
    except Exception as exc:
        return CheckResult("playwright MCP", "warn", str(exc))


def run_doctor(
    workspace: Path,
    *,
    verify_mcp: bool = False,
) -> list[CheckResult]:
    workspace = workspace.resolve()
    load_dotenv_files(workspace)
    checks: list[Callable[[], CheckResult]] = [
        _check_package_import,
        _check_pytest_plugin,
        _check_cursor_sdk,
        _check_playwright_browsers,
        _check_npx,
        lambda: _check_mcp_json(workspace),
        lambda: _check_api_key(workspace),
        lambda: _check_config(workspace),
        lambda: _check_artifact_dirs(workspace),
        lambda: _check_skills(workspace),
    ]
    results = [fn() for fn in checks]
    if verify_mcp:
        results.append(verify_playwright_mcp())
    return results


def format_report(results: list[CheckResult]) -> str:
    lines = ["Healing doctor", ""]
    for r in results:
        mark = {"ok": "OK  ", "warn": "WARN", "error": "FAIL"}[r.status]
        lines.append(f"  [{mark}] {r.name}: {r.detail}")
    errors = sum(1 for r in results if r.status == "error")
    warns = sum(1 for r in results if r.status == "warn")
    lines.append("")
    lines.append(f"Summary: {errors} error(s), {warns} warning(s)")
    if any(r.name == "CURSOR_API_KEY" and r.status == "warn" for r in results):
        lines.append("Note: failure capture, scan, stub propose, review, and apply work without CURSOR_API_KEY.")
        lines.append("      Automated MCP propose (mcp_propose_runner / HEALING_MCP_AUTO) needs the key.")
    if any(r.name == "mcp.json" for r in results):
        lines.append("Note: Cursor Settings → MCP is only for interactive IDE use.")
        lines.append("      CLI mcp_propose_runner starts Playwright MCP via stdio on its own.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check consumer setup for the healing package.")
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument(
        "--verify-mcp",
        action="store_true",
        help="Run npx @playwright/mcp@latest --help (may download; needs network).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as errors.",
    )
    args = parser.parse_args()
    results = run_doctor(args.workspace, verify_mcp=args.verify_mcp)
    print(format_report(results))
    if any(r.status == "error" for r in results):
        return 1
    if args.strict and any(r.status == "warn" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
