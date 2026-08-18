"""Apply healing-queue POM patches to pages/*.py."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def _allowed_file(path: Path, workspace: Path) -> bool:
    from healing.config import load_config

    cfg = load_config(workspace)
    rel = path.resolve().relative_to(workspace.resolve())
    parts = rel.parts
    if not parts or path.suffix != ".py":
        return False
    return parts[0] in cfg.apply_roots


def _property_return_pattern(symbol: str) -> re.Pattern[str]:
    return re.compile(
        rf"(@property\s+def\s+{re.escape(symbol)}\s*\([^)]*\)(?:\s*->[^:]*)?:\s*"
        rf"(?:\n\s+\"\"\"[\s\S]*?\"\"\"\s*)?"
        rf"\n\s*return\s+)(.+)"
    )


def apply_architecture_update(
    workspace: Path,
    update: dict[str, Any],
    *,
    dry_run: bool = False,
) -> str:
    file_path = workspace / update["file"]
    if not _allowed_file(file_path, workspace):
        raise ValueError(f"Refusing to edit outside apply_roots: {update['file']}")

    if not file_path.exists():
        raise FileNotFoundError(f"Page file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    before = update.get("before", "")
    after = update.get("after", "")
    symbol = update.get("symbol", "")

    new_content = content
    message = ""

    # Prefer symbol-based property update when symbol + after are present.
    if symbol and after:
        match = _property_return_pattern(symbol).search(content)
        if match:
            new_content = content[: match.start(2)] + after + content[match.end(2) :]
            message = f"Updated property '{symbol}' return in {update['file']}"
        elif before and before in content:
            new_content = content.replace(before, after, 1)
            message = f"Replaced locator expression for '{symbol}' in {update['file']}"
        else:
            raise ValueError(f"Could not locate property '{symbol}' in {update['file']}")
    elif before and after and before in content:
        new_content = content.replace(before, after, 1)
        message = f"Replaced locator expression for '{symbol}' in {update['file']}"
    else:
        raise ValueError(f"Insufficient update data for symbol '{symbol}'")

    if new_content == content:
        raise ValueError(f"No changes applied for '{symbol}'")

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")
    return message


_CI_PYTHON_RE = re.compile(
    r"/opt/hostedtoolcache/Python/\S+?/python(?:\d[\d.]*)?"
)
_RUNNER_ROOT_RE = re.compile(r"/home/runner/work/[^/\s]+/[^/\s]+/")


def is_validation_command_allowed(argv: list[str]) -> bool:
    """True when argv is an allowlisted pytest / healing module invocation."""
    if not argv:
        return False
    first = Path(argv[0]).name.lower()
    if first in ("pytest", "py.test", "pytest.exe"):
        return True
    if first.startswith("python"):
        if len(argv) >= 3 and argv[1] == "-m" and argv[2] == "pytest":
            return True
        if len(argv) >= 3 and argv[1] == "-m" and argv[2].startswith("healing."):
            return True
        return False
    return False


def relative_pytest_target(spec: str, workspace: Path) -> str:
    """Turn a CI absolute test path or nodeid into a workspace-relative pytest target."""
    text = spec.strip().replace("\\", "/")
    text = _RUNNER_ROOT_RE.sub("", text)
    path_part, sep, rest = text.partition("::")
    path_part = path_part.strip()
    try:
        candidate = Path(path_part)
        if candidate.is_absolute():
            path_part = str(candidate.resolve().relative_to(workspace.resolve()))
    except (ValueError, OSError):
        marker = "tests/"
        idx = path_part.find(marker)
        if idx >= 0:
            path_part = path_part[idx:]
    if sep:
        return f"{path_part}{sep}{rest}"
    return path_part


def normalize_validation_command(
    cmd: str,
    workspace: Path,
    *,
    failure_id: str | None = None,
    test_file: str | None = None,
    nodeid: str | None = None,
) -> str:
    """Rewrite CI-origin validation commands so they run in this workspace."""
    workspace = workspace.resolve()
    if failure_id and not (nodeid or test_file):
        try:
            from healing.healing_queue import load_failure_payload

            failure = load_failure_payload(failure_id)
            test = failure.get("test") or {}
            nodeid = nodeid or test.get("nodeid")
            test_file = test_file or test.get("file")
        except (FileNotFoundError, OSError, TypeError, ValueError):
            pass

    argv: list[str] = []
    try:
        argv = shlex.split(cmd)
    except ValueError:
        argv = []

    extra_flags: list[str] = []
    i = 0
    if argv:
        name = Path(argv[0]).name.lower()
        if name.startswith("python"):
            i = 1
            if i + 1 < len(argv) and argv[i] == "-m" and argv[i + 1] in ("pytest", "py.test"):
                i += 2
        elif name in ("pytest", "py.test", "pytest.exe"):
            i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in ("-q", "--quiet"):
            i += 1
            continue
        if arg.endswith(".py") or "::" in arg or "/tests/" in arg.replace("\\", "/") or arg.startswith("tests/"):
            i += 1
            continue
        extra_flags.append(arg)
        i += 1

    target = ""
    if nodeid:
        target = relative_pytest_target(str(nodeid), workspace)
    elif test_file:
        target = relative_pytest_target(str(test_file), workspace)
    else:
        for arg in argv:
            if arg.endswith(".py") or "::" in arg or "/tests/" in arg.replace("\\", "/") or arg.startswith("tests/"):
                target = relative_pytest_target(arg, workspace)
                break

    if not target:
        rewritten = _CI_PYTHON_RE.sub(sys.executable, cmd)
        return _RUNNER_ROOT_RE.sub(str(workspace) + "/", rewritten)

    out = [sys.executable, "-m", "pytest", target, "-q", *extra_flags]
    return shlex.join(out)


def parse_validation_command(validation_cmd: str) -> list[str]:
    """Split validation command and reject shell metacharacters / disallowed argv."""
    try:
        argv = shlex.split(validation_cmd)
    except ValueError as exc:
        raise ValueError(f"Invalid validation_command: {exc}") from exc
    if not is_validation_command_allowed(argv):
        raise ValueError(
            "validation_command must be an allowlisted invocation "
            "(pytest, python -m pytest, or python -m healing.*); "
            f"got: {validation_cmd!r}"
        )
    return argv


def apply_patch_payload(
    payload: dict[str, Any],
    *,
    workspace: Path,
    dry_run: bool = False,
    run_validation: bool = True,
) -> list[str]:
    proposal = payload.get("proposal") or payload
    updates = proposal.get("architecture_updates") or payload.get("architecture_updates") or []
    if not updates:
        raise ValueError("Patch has no architecture_updates.")

    # Snapshot originals before any writes so validation failure can roll back.
    snapshots: dict[Path, str] = {}
    if not dry_run:
        for update in updates:
            file_path = (workspace / update["file"]).resolve()
            if file_path not in snapshots and file_path.exists():
                snapshots[file_path] = file_path.read_text(encoding="utf-8")

    messages: list[str] = []
    try:
        for update in updates:
            messages.append(apply_architecture_update(workspace, update, dry_run=dry_run))

        validation_cmd = proposal.get("validation_command") or payload.get("validation_command")
        if run_validation and validation_cmd and not dry_run:
            from healing.doctor import load_dotenv_files

            load_dotenv_files(workspace)
            validation_cmd = normalize_validation_command(
                str(validation_cmd),
                workspace,
                failure_id=proposal.get("failure_id"),
            )
            argv = parse_validation_command(validation_cmd)
            result = subprocess.run(
                argv,
                shell=False,
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Validation failed ({validation_cmd}):\n{result.stdout}\n{result.stderr}"
                )
            messages.append(f"Validation passed: {validation_cmd}")
    except Exception:
        if not dry_run:
            for path, original in snapshots.items():
                path.write_text(original, encoding="utf-8")
        raise

    return messages


def load_patch(patch_id: str, patches_dir: Path) -> dict[str, Any]:
    path = patches_dir / f"{patch_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Patch not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    from healing.paths import QUEUE_PATCHES

    parser = argparse.ArgumentParser(description="Apply POM healing patch to pages/*.py")
    parser.add_argument("--patch-id", required=True)
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    payload = load_patch(args.patch_id, QUEUE_PATCHES)
    try:
        messages = apply_patch_payload(
            payload,
            workspace=workspace,
            dry_run=args.dry_run,
            run_validation=not args.no_validate,
        )
        for msg in messages:
            print(f"[ok] {msg}")
        return 0
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"[error] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
