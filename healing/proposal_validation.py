"""Run proposal validation_command against a patched registry copy."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from healing.apply_suggestion import _load_registry, _save_registry
from healing.resolved_apply import apply_proposal_to_registry, extract_proposal


@dataclass
class ValidationResult:
    command: str
    exit_code: int
    passed: bool
    stdout: str
    stderr: str
    registry_temp_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_validation_command(command: str) -> str:
    cmd = command.strip()
    if cmd.startswith("pytest ") or cmd == "pytest":
        return cmd.replace("pytest", f"{sys.executable} -m pytest", 1)
    return cmd


def _default_validation_command(proposal: dict[str, Any], semantic_key: str) -> str:
    cmd = proposal.get("validation_command")
    if isinstance(cmd, str) and cmd.strip():
        return _normalize_validation_command(cmd.strip())
    slug = semantic_key.replace(".", "_")
    return f"{sys.executable} -m pytest -q tests/test_demo_buttons_links.py"


def validate_proposal_patch(
    *,
    payload: dict[str, Any],
    workspace: Path,
    registry_path: Path,
    timeout_seconds: int = 300,
) -> ValidationResult:
    """
    Apply proposal to a temp registry copy and run validation_command in workspace.
    """
    proposal = extract_proposal(payload)
    semantic_key = str(proposal.get("semantic_key", "unknown"))
    command = _default_validation_command(proposal, semantic_key)

    registry = _load_registry(registry_path)
    patched = deepcopy(registry)
    try:
        apply_proposal_to_registry(patched, payload)
    except ValueError as exc:
        return ValidationResult(
            command=command,
            exit_code=1,
            passed=False,
            stdout="",
            stderr=f"Could not apply patch for validation: {exc}",
            registry_temp_path=None,
        )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix="healing-registry-",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        yaml.safe_dump(patched, tmp, sort_keys=False)
        temp_registry = tmp.name

    env = os.environ.copy()
    env["HEALING_REGISTRY_PATH"] = temp_registry

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
        stdout = completed.stdout[-8000:] if completed.stdout else ""
        stderr = completed.stderr[-8000:] if completed.stderr else ""
        return ValidationResult(
            command=command,
            exit_code=completed.returncode,
            passed=completed.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            registry_temp_path=temp_registry,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ValidationResult(
            command=command,
            exit_code=124,
            passed=False,
            stdout=stdout[-8000:],
            stderr=(stderr + "\nValidation timed out.")[-8000:],
            registry_temp_path=temp_registry,
        )
    finally:
        try:
            Path(temp_registry).unlink(missing_ok=True)
        except OSError:
            pass
