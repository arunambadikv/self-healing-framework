"""Emit healing events for CI ratio monitoring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from healing.paths import ensure_queue_dirs

REPORTS_DIR = Path("artifacts/healing-reports")


def _report_path(test_module: str) -> Path:
    safe = test_module.replace("/", "_").replace("\\", "_") or "unknown"
    return REPORTS_DIR / f"{safe}.json"


def append_event(
    test_module: str,
    *,
    status: str,
    key: str,
    action: str,
    message: str = "",
    details: dict[str, Any] | None = None,
) -> Path:
    """Append a healing event to the per-test-module report file."""
    ensure_queue_dirs()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _report_path(test_module)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"events": []}
    data.setdefault("events", []).append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "key": key,
            "action": action,
            "message": message,
            "details": details or {},
        }
    )
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def emit_failure_captured(payload: dict[str, Any]) -> None:
    test = payload.get("test") or {}
    module = Path(str(test.get("file", "unknown"))).stem
    append_event(
        module,
        status="failed",
        key=payload.get("architecture_ref") or test.get("nodeid", "unknown"),
        action="capture",
        message=str((payload.get("error") or {}).get("message", ""))[:300],
        details={
            "failure_id": payload.get("failure_id"),
            "classification": payload.get("classification"),
        },
    )


def emit_patch_ready(patch_id: str, proposal: dict[str, Any]) -> None:
    failure_id = proposal.get("failure_id", "")
    key = (proposal.get("architecture_updates") or [{}])[0].get("symbol", patch_id)
    append_event(
        Path(str(proposal.get("validation_command", ""))).stem or "healing",
        status="primary",
        key=key,
        action="propose_complete",
        message=f"Patch {patch_id} ready for review",
        details={"patch_id": patch_id, "failure_id": failure_id},
    )


def emit_patch_applied(patch_id: str, proposal: dict[str, Any]) -> None:
    key = (proposal.get("architecture_updates") or [{}])[0].get("symbol", patch_id)
    append_event(
        "healing",
        status="healed",
        key=key,
        action="apply",
        message=f"Applied patch {patch_id}",
        details={"patch_id": patch_id, "failure_id": proposal.get("failure_id")},
    )


def emit_patch_skipped(patch_id: str, proposal: dict[str, Any], reason: str) -> None:
    key = (proposal.get("architecture_updates") or [{}])[0].get("symbol", patch_id)
    append_event(
        "healing",
        status="failed",
        key=key,
        action="skip",
        message=reason,
        details={"patch_id": patch_id, "failure_id": proposal.get("failure_id")},
    )
