"""Merge `gh run download` CI artifacts into the local pomhealer-artifacts tree."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pomhealer.pom_apply import normalize_validation_command, relative_pytest_target

KNOWN_DOWNLOAD_NAMES = ("pomhealer-pipeline-e2e", "pomhealer-artifacts")
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "pomhealer",
        "pages",
        "tests",
        "docs",
        "scripts",
        ".cursor",
        "pomhealer-artifacts",
        "__pycache__",
        ".pytest_cache",
        "artifacts",
    }
)
SKIP_FILENAMES = frozenset({"index.json.lock"})
TEXT_SUFFIXES = {".json", ".md"}


@dataclass
class DownloadRoot:
    """A detected `gh run download` directory."""

    name: str
    layout: Path
    cleanup: Path


@dataclass
class ImportResult:
    sources: list[str] = field(default_factory=list)
    failures: int = 0
    patches: int = 0
    index_upserts: int = 0
    rewritten: int = 0
    cleaned: list[str] = field(default_factory=list)

    @property
    def imported(self) -> bool:
        return bool(self.sources) and (
            self.failures > 0 or self.patches > 0 or self.index_upserts > 0 or self.rewritten > 0
        )

    def summary_line(self) -> str:
        src = ", ".join(f"{name}/" for name in self.sources) or "(none)"
        return (
            f"[pomhealer] imported {self.failures} failures, {self.patches} patches from {src}"
        )


def _artifacts_dir(workspace: Path) -> Path:
    from pomhealer.config import load_config

    cfg = load_config(workspace)
    return (workspace / cfg.artifacts_dir).resolve()


def resolve_artifact_layout(path: Path) -> Path | None:
    """Return the directory that contains failures/ and pomhealer-queue/, if any."""
    if not path.is_dir():
        return None
    if (path / "failures").is_dir() and (path / "pomhealer-queue").is_dir():
        return path.resolve()
    nested = path / "pomhealer-artifacts"
    if (nested / "failures").is_dir() and (nested / "pomhealer-queue").is_dir():
        return nested.resolve()
    return None


def detect_download_roots(workspace: Path) -> list[DownloadRoot]:
    """Find CI download folders that are not the live pomhealer-artifacts tree."""
    workspace = workspace.resolve()
    live = _artifacts_dir(workspace)
    found: list[DownloadRoot] = []
    seen: set[Path] = set()

    def _add(name: str, candidate: Path) -> None:
        layout = resolve_artifact_layout(candidate)
        if layout is None:
            return
        if layout == live:
            return
        if layout in seen:
            return
        seen.add(layout)
        found.append(DownloadRoot(name=name, layout=layout, cleanup=candidate.resolve()))

    for name in KNOWN_DOWNLOAD_NAMES:
        _add(name, workspace / name)

    for child in sorted(workspace.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name in SKIP_DIR_NAMES or child.name.startswith("."):
            continue
        if child.name in KNOWN_DOWNLOAD_NAMES:
            continue
        _add(child.name, child)
    return found


def rewrite_ci_paths(text: str, workspace: Path) -> str:
    """Replace GitHub Actions runner paths with this workspace."""
    from pomhealer.pom_apply import _CI_PYTHON_RE, _RUNNER_ROOT_RE

    workspace = workspace.resolve()
    text = _RUNNER_ROOT_RE.sub(str(workspace) + "/", text)
    text = _CI_PYTHON_RE.sub(sys_executable(), text)
    return text


def sys_executable() -> str:
    import sys

    return sys.executable


def _rewrite_json_payload(data: Any, workspace: Path) -> Any:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if key == "validation_command" and isinstance(value, str):
                rewritten = rewrite_ci_paths(value, workspace)
                failure_id = data.get("failure_id")
                out[key] = normalize_validation_command(
                    rewritten, workspace, failure_id=failure_id if isinstance(failure_id, str) else None
                )
            elif key in {"file", "nodeid"} and isinstance(value, str) and (
                "/tests/" in value.replace("\\", "/") or value.startswith("tests/") or value.endswith(".py")
            ):
                out[key] = relative_pytest_target(rewrite_ci_paths(value, workspace), workspace)
            elif isinstance(value, str):
                out[key] = rewrite_ci_paths(value, workspace)
            else:
                out[key] = _rewrite_json_payload(value, workspace)
        return out
    if isinstance(data, list):
        return [_rewrite_json_payload(item, workspace) for item in data]
    if isinstance(data, str):
        return rewrite_ci_paths(data, workspace)
    return data


def rewrite_artifact_file(path: Path, workspace: Path) -> bool:
    """Rewrite CI paths in a JSON or Markdown artifact. Returns True if changed."""
    if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
        return False
    original = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(original)
        except json.JSONDecodeError:
            updated = rewrite_ci_paths(original, workspace)
        else:
            updated = json.dumps(_rewrite_json_payload(payload, workspace), indent=2, ensure_ascii=True)
            if not original.endswith("\n"):
                pass
            else:
                updated += "\n"
    else:
        updated = rewrite_ci_paths(original, workspace)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def _copy_newer(src: Path, dest: Path, *, dry_run: bool) -> int:
    if not src.is_dir():
        return 0
    copied = 0
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        if path.name in SKIP_FILENAMES:
            continue
        rel = path.relative_to(src)
        dest_path = dest / rel
        if dest_path.exists() and dest_path.stat().st_mtime >= path.stat().st_mtime:
            continue
        copied += 1
        if not dry_run:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest_path)
    return copied


def _localize_index_entry(entry: dict[str, Any], artifacts: Path) -> dict[str, Any]:
    localized = dict(entry)
    failure_id = str(entry.get("failure_id") or "")
    patch_id = str(entry.get("patch_id") or "")
    failures = artifacts / "failures"
    queue = artifacts / "pomhealer-queue"
    search_patch_dirs = [queue / "patches", queue / "applied", queue / "skipped"]

    def _existing(name: str, directories: Iterable[Path]) -> str | None:
        for directory in directories:
            candidate = directory / name
            if candidate.is_file():
                return str(candidate.resolve())
        return None

    if failure_id:
        json_path = _existing(f"{failure_id}.json", [failures])
        md_path = _existing(f"{failure_id}.md", [failures])
        if json_path:
            localized["failure_json"] = json_path
        if md_path:
            localized["failure_md"] = md_path
    if patch_id:
        json_path = _existing(f"{patch_id}.json", search_patch_dirs)
        md_path = _existing(f"{patch_id}.md", search_patch_dirs)
        if json_path:
            localized["patch_json"] = json_path
        if md_path:
            localized["patch_md"] = md_path
    return localized


def _rewrite_tree(root: Path, workspace: Path) -> int:
    if not root.is_dir():
        return 0
    changed = 0
    for path in root.rglob("*"):
        if rewrite_artifact_file(path, workspace):
            changed += 1
    return changed


def import_ci_artifacts(
    workspace: Path,
    *,
    source: Path | None = None,
    dry_run: bool = False,
    cleanup: bool = False,
) -> ImportResult:
    """Detect CI download dirs and merge them into pomhealer-artifacts/."""
    from pomhealer.queue import merge_index_entries
    from pomhealer.paths import configure_workspace, ensure_queue_dirs

    workspace = configure_workspace(workspace.resolve())
    ensure_queue_dirs()
    artifacts = _artifacts_dir(workspace)
    result = ImportResult()

    if source is not None:
        source = source.resolve()
        layout = resolve_artifact_layout(source)
        if layout is None:
            return result
        roots = [DownloadRoot(name=source.name, layout=layout, cleanup=source)]
    else:
        roots = detect_download_roots(workspace)

    if not roots:
        return result

    for root in roots:
        result.sources.append(root.name)
        result.failures += _copy_newer(
            root.layout / "failures", artifacts / "failures", dry_run=dry_run
        )
        result.patches += _copy_newer(
            root.layout / "pomhealer-queue" / "patches",
            artifacts / "pomhealer-queue" / "patches",
            dry_run=dry_run,
        )
        for sub in ("applied", "skipped", "summaries"):
            _copy_newer(
                root.layout / "pomhealer-queue" / sub,
                artifacts / "pomhealer-queue" / sub,
                dry_run=dry_run,
            )
        for sub in ("architecture", "pomhealer-reports", "auth"):
            _copy_newer(root.layout / sub, artifacts / sub, dry_run=dry_run)

        if not dry_run:
            result.rewritten += _rewrite_tree(artifacts / "failures", workspace)
            result.rewritten += _rewrite_tree(artifacts / "pomhealer-queue", workspace)

            incoming_index = root.layout / "pomhealer-queue" / "index.json"
            if incoming_index.is_file():
                try:
                    payload = json.loads(incoming_index.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    payload = {}
                entries = payload.get("entries") if isinstance(payload, dict) else None
                if isinstance(entries, list):
                    localized = [_localize_index_entry(e, artifacts) for e in entries if isinstance(e, dict)]
                    result.index_upserts += merge_index_entries(localized)

            if cleanup and root.cleanup.exists() and root.cleanup != workspace and root.cleanup != artifacts:
                shutil.rmtree(root.cleanup)
                result.cleaned.append(root.name)

    if not dry_run:
        from pomhealer.queue import archive_terminal_patch_files

        archive_terminal_patch_files()
    return result


def download_dir_is_newer(workspace: Path, root: DownloadRoot) -> bool:
    """True when the download queue index is newer than the local index."""
    incoming = root.layout / "pomhealer-queue" / "index.json"
    local = _artifacts_dir(workspace) / "pomhealer-queue" / "index.json"
    if not incoming.is_file():
        return False
    if not local.is_file():
        return True
    return incoming.stat().st_mtime > local.stat().st_mtime


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge gh-run-download CI artifacts into pomhealer-artifacts/."
    )
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument(
        "--from",
        dest="source",
        type=Path,
        help="Download directory to import (default: auto-detect).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would be imported.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove the download directory after a successful merge.",
    )
    args = parser.parse_args()
    from pomhealer.paths import configure_workspace

    workspace = configure_workspace(args.workspace.resolve())
    result = import_ci_artifacts(
        workspace,
        source=args.source,
        dry_run=args.dry_run,
        cleanup=args.cleanup,
    )
    if not result.sources:
        print("[pomhealer] no CI download directories found")
        return 0
    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}{result.summary_line()}")
    if result.cleaned:
        print(f"[pomhealer] removed download dir(s): {', '.join(result.cleaned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
