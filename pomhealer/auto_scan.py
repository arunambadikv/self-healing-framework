"""Auto-run architecture discovery after install/update or when the manifest is stale."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any

from pomhealer.paths import ARCHITECTURE_DIR, MANIFEST_JSON, ensure_queue_dirs


def installed_pomhealer_version() -> str:
    try:
        return metadata.version("pomhealer")
    except Exception:
        return "0+unknown"


def package_version_stamp_path() -> Path:
    return Path(str(ARCHITECTURE_DIR)) / ".pomhealer-package-version"


def read_package_version_stamp() -> str | None:
    path = package_version_stamp_path()
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def write_package_version_stamp(version: str | None = None) -> Path:
    ensure_queue_dirs()
    path = package_version_stamp_path()
    path.write_text((version or installed_pomhealer_version()) + "\n", encoding="utf-8")
    return path


def _has_pages(workspace: Path) -> bool:
    pages = workspace / "pages"
    return pages.is_dir() and any(pages.glob("*.py"))


def should_auto_architecture_discovery(workspace: Path) -> tuple[bool, str]:
    """Return (should_run, reason) for an automatic architecture scan."""
    workspace = workspace.resolve()
    if not _has_pages(workspace):
        return False, "no pages/*.py yet"

    version = installed_pomhealer_version()
    stamp = read_package_version_stamp()
    if stamp != version:
        if stamp is None:
            return True, f"package install (pomhealer {version}); architecture manifest needed"
        return True, f"package updated (pomhealer {stamp} → {version})"

    if not Path(str(MANIFEST_JSON)).exists():
        return True, "architecture manifest missing"

    from pomhealer.post_test import manifest_is_stale

    if manifest_is_stale(workspace):
        return True, "architecture manifest stale vs pages/tests/data"

    return False, "architecture manifest up to date"


def run_auto_architecture_discovery(
    workspace: Path,
    *,
    force: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run architecture_scan when install/update/stale (or force=True).

    Called from pomhealer-init and pytest session start so consumers do not need
    a separate /architecture-discovery step after pip install -U.
    """
    workspace = workspace.resolve()
    if force:
        should, reason = True, "forced"
    else:
        should, reason = should_auto_architecture_discovery(workspace)

    if not should:
        return {"ran": False, "reason": reason}

    from pomhealer.architecture_scan import build_manifest, write_manifest
    from pomhealer.paths import configure_workspace

    configure_workspace(workspace)
    ensure_queue_dirs()
    version = installed_pomhealer_version()
    manifest = build_manifest(workspace)
    json_path, md_path, changed = write_manifest(manifest, workspace)
    write_package_version_stamp(version)

    result = {
        "ran": True,
        "reason": reason,
        "changed": changed,
        "content_hash": manifest.get("content_hash"),
        "package_version": version,
        "json": str(json_path),
        "md": str(md_path),
    }
    if not quiet:
        action = "updated" if changed else "refreshed (hash unchanged)"
        print(
            f"[pomhealer] architecture-discovery {action}: "
            f"hash={manifest.get('content_hash')} ({reason})"
        )
    return result
