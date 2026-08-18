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


PLAYWRIGHT_BROWSERS_DIR = ".playwright-browsers"
SANDBOX_BROWSERS_MARKERS = ("cursor-sandbox-cache",)


def load_dotenv_files(workspace: Path) -> list[Path]:
    """Load workspace .env into os.environ (does not override existing vars)."""
    loaded: list[Path] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        apply_persistent_browsers_path(workspace)
        return loaded
    for name in (".env", ".env.local"):
        path = workspace / name
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(path)
    apply_persistent_browsers_path(workspace)
    return loaded


def _dotenv_value(workspace: Path, key: str) -> str:
    for name in (".env", ".env.local"):
        path = workspace / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, _, value = stripped.partition("=")
            if k.strip() == key:
                return value.strip().strip("'\"")
    return ""


def apply_persistent_browsers_path(workspace: Path) -> str | None:
    """Prefer a project-local Playwright cache over Cursor's ephemeral sandbox path."""
    desired = _dotenv_value(workspace, "PLAYWRIGHT_BROWSERS_PATH")
    if not desired:
        return None
    current = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if current and current != "0" and not any(m in current for m in SANDBOX_BROWSERS_MARKERS):
        return current
    path = Path(desired)
    if not path.is_absolute():
        path = workspace / path
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(path)
    return str(path)


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


def _playwright_browser_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env and env != "0":
        roots.append(Path(env))
    home = Path.home()
    roots.extend(
        [
            home / ".cache" / "ms-playwright",
            home / "Library" / "Caches" / "ms-playwright",
            Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",
        ]
    )
    # Dedupe while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        out.append(root)
    return out


def find_chromium_in_root(root: Path) -> Path | None:
    """Locate Chromium under a single Playwright browsers root."""
    if not root.is_dir():
        return None
    patterns = (
        "chromium-*/chrome-linux*/chrome",
        "chromium_headless_shell-*/chrome-linux*/headless_shell",
        "chromium-*/chrome-mac*/Chromium",
        "chromium-*/chrome-mac*/Google Chrome for Testing",
        "chromium-*/chrome-win*/chrome.exe",
        "chromium-*/chrome-win*/chrome",
    )
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(p for p in root.glob(pattern) if p.is_file())
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def find_chromium_executable() -> Path | None:
    """Locate an installed Chromium binary without starting a Playwright driver."""
    candidates: list[Path] = []
    for root in _playwright_browser_roots():
        found = find_chromium_in_root(root)
        if found is not None:
            candidates.append(found)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _check_playwright_browsers() -> CheckResult:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return CheckResult("playwright", "error", "playwright not installed")

    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env and any(m in env for m in SANDBOX_BROWSERS_MARKERS):
        return CheckResult(
            "chromium",
            "warn",
            "Cursor sandbox cache is ephemeral; set PLAYWRIGHT_BROWSERS_PATH="
            f"{PLAYWRIGHT_BROWSERS_DIR} in .env",
        )

    if env and env != "0":
        env_root = Path(env)
        found = find_chromium_in_root(env_root)
        if found is not None:
            return CheckResult("chromium", "ok", f"executable at {found} (root {env_root})")
        home_found = None
        for root in _playwright_browser_roots()[1:]:
            home_found = find_chromium_in_root(root)
            if home_found is not None:
                break
        if home_found is not None:
            return CheckResult(
                "chromium",
                "warn",
                f"PLAYWRIGHT_BROWSERS_PATH={env} has no Chromium, but {home_found} exists — "
                f"unset the env var or set PLAYWRIGHT_BROWSERS_PATH={PLAYWRIGHT_BROWSERS_DIR} "
                "and run: playwright install chromium",
            )
        return CheckResult(
            "chromium",
            "warn",
            f"chromium executable missing under PLAYWRIGHT_BROWSERS_PATH={env} — "
            "run: playwright install chromium",
        )

    path = find_chromium_executable()
    if path is not None:
        return CheckResult("chromium", "ok", f"executable at {path}")
    return CheckResult(
        "chromium",
        "warn",
        "chromium executable missing — run: playwright install chromium",
    )


def _check_ci_download_dirs(workspace: Path) -> CheckResult:
    from healing.artifact_import import detect_download_roots, download_dir_is_newer

    roots = detect_download_roots(workspace)
    newer = [r.name for r in roots if download_dir_is_newer(workspace, r)]
    if newer:
        names = ", ".join(f"{n}/" for n in newer)
        return CheckResult(
            "CI downloads",
            "warn",
            f"{names} newer than local queue — run healing-import or healing-review to merge",
        )
    if roots:
        names = ", ".join(f"{r.name}/" for r in roots)
        return CheckResult(
            "CI downloads",
            "ok",
            f"leftover {names} (already imported or not newer); healing-import --cleanup to remove",
        )
    return CheckResult("CI downloads", "ok", "no leftover gh run download directories")


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
    from healing.llm_config import KEY_ENV_VARS, LlmConfigError, resolve_llm_config

    load_dotenv_files(workspace)
    try:
        cfg = resolve_llm_config()
    except LlmConfigError as exc:
        return CheckResult("LLM provider", "warn", str(exc))

    if cfg.has_key:
        return CheckResult(
            "LLM API key",
            "ok",
            f"{cfg.key_env} set for provider={cfg.provider} (model={cfg.model})",
        )
    others = [v for p, v in KEY_ENV_VARS.items() if p != cfg.provider and os.environ.get(v, "").strip()]
    hint = (
        f"set {cfg.key_env} for HEALING_LLM_PROVIDER={cfg.provider} "
        "(capture/review work without it)"
    )
    if others:
        hint += f"; note: other keys present ({', '.join(others)}) but unused for this provider"
    env_example = workspace / ".env.example"
    if env_example.exists():
        hint += f" — see {env_example.name}"
    return CheckResult("LLM API key", "warn", hint)


def _check_provider_sdk(workspace: Path) -> CheckResult:
    from healing.llm_config import LlmConfigError, resolve_llm_config

    load_dotenv_files(workspace)
    try:
        cfg = resolve_llm_config()
    except LlmConfigError as exc:
        return CheckResult("LLM SDK", "warn", str(exc))

    if cfg.provider == "cursor":
        return _check_cursor_sdk()
    if cfg.provider == "openai":
        try:
            import openai  # noqa: F401
            import mcp  # noqa: F401

            return CheckResult("LLM SDK", "ok", "openai + mcp installed")
        except ImportError:
            return CheckResult(
                "LLM SDK",
                "warn",
                "pip install 'healing[openai]' or 'healing[propose]' for OpenAI propose",
            )
    if cfg.provider == "anthropic":
        try:
            import anthropic  # noqa: F401
            import mcp  # noqa: F401

            return CheckResult("LLM SDK", "ok", "anthropic + mcp installed")
        except ImportError:
            return CheckResult(
                "LLM SDK",
                "warn",
                "pip install 'healing[anthropic]' or 'healing[propose]' for Anthropic propose",
            )
    return CheckResult("LLM SDK", "warn", f"unknown provider {cfg.provider}")


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


def _check_pages_dir(workspace: Path) -> CheckResult:
    from healing.config import load_config
    from healing.paths import configure_workspace

    configure_workspace(workspace)
    cfg = load_config(workspace)
    pages = workspace / cfg.pages_dir
    if pages.is_dir() and any(pages.glob("*.py")):
        return CheckResult("pages dir", "ok", f"{cfg.pages_dir}/ with Python page objects")
    if pages.is_dir():
        return CheckResult("pages dir", "warn", f"{cfg.pages_dir}/ exists but has no .py files")
    return CheckResult("pages dir", "warn", f"{cfg.pages_dir}/ missing — create page objects or run healing-init")


def _check_env_not_tracked(workspace: Path) -> CheckResult:
    env_path = workspace / ".env"
    if not env_path.is_file():
        return CheckResult(".env tracked", "ok", "no .env file (or not present yet)")
    git = shutil.which("git")
    if not git:
        return CheckResult(".env tracked", "ok", ".env present (git not available to verify)")
    try:
        tracked = subprocess.run(
            [git, "-C", str(workspace), "ls-files", "--error-unmatch", ".env"],
            capture_output=True,
            text=True,
            check=False,
        )
        if tracked.returncode == 0:
            return CheckResult(
                ".env tracked",
                "warn",
                ".env is tracked by git — remove it from the index and rely on .env.example",
            )
        return CheckResult(".env tracked", "ok", ".env present and not tracked by git")
    except Exception as exc:
        return CheckResult(".env tracked", "warn", f"could not check git tracking: {exc}")


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
    """Optional live check: npx can resolve the pinned @playwright/mcp package."""
    from healing.mcp_constants import PLAYWRIGHT_MCP_PACKAGE

    npx = shutil.which("npx")
    if not npx:
        return CheckResult("playwright MCP", "warn", "skipped — npx not available")
    try:
        proc = subprocess.run(
            [npx, "--yes", PLAYWRIGHT_MCP_PACKAGE, "--help"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode == 0:
            return CheckResult(
                "playwright MCP", "ok", f"npx {PLAYWRIGHT_MCP_PACKAGE} responded"
            )
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
        lambda: _check_provider_sdk(workspace),
        _check_playwright_browsers,
        _check_npx,
        lambda: _check_mcp_json(workspace),
        lambda: _check_api_key(workspace),
        lambda: _check_config(workspace),
        lambda: _check_pages_dir(workspace),
        lambda: _check_artifact_dirs(workspace),
        lambda: _check_ci_download_dirs(workspace),
        lambda: _check_env_not_tracked(workspace),
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
    if any(r.name == "LLM API key" and r.status == "warn" for r in results):
        lines.append(
            "Note: failure capture, scan, stub propose, review, and apply work without an LLM key."
        )
        lines.append(
            "      Automated MCP propose needs HEALING_LLM_PROVIDER + matching key "
            "(CURSOR_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)."
        )
    if any(r.name == "mcp.json" for r in results):
        lines.append("Note: Cursor Settings → MCP is only for interactive IDE use.")
        lines.append("      CLI mcp_propose_runner starts Playwright MCP via stdio on its own.")
    lines.append(
        "Note: architecture-discovery runs automatically on healing-init and on the next "
        "pytest after a package install/update (or when the manifest is stale)."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check consumer setup for the healing package.")
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument(
        "--verify-mcp",
        action="store_true",
        help="Run npx for the pinned @playwright/mcp package --help (may download; needs network).",
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
