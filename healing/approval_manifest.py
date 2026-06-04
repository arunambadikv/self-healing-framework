"""Approval manifest for Phase C resolved proposals (approve/reject per semantic key)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from healing.resolved_apply import extract_proposal


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Approval manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Approval manifest must be a JSON object.")
    return data


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(manifest), encoding="utf-8")


def build_manifest_from_resolved(resolved_dir: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted(resolved_dir.glob("*.json")):
        if path.name == "approval-manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        proposal = extract_proposal(payload)
        semantic_key = proposal.get("semantic_key", path.stem)
        validation = payload.get("validation") or proposal.get("validation") or {}
        entries.append(
            {
                "semantic_key": semantic_key,
                "resolved_file": str(path.resolve()),
                "status": "pending",
                "validation_passed": bool(validation.get("passed")),
                "validation_command": validation.get("command") or proposal.get("validation_command"),
                "reviewer": None,
                "notes": "",
            }
        )

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "resolved_dir": str(resolved_dir.resolve()),
        "entries": entries,
    }


def init_manifest(*, resolved_dir: Path, manifest_path: Path, overwrite: bool) -> dict[str, Any]:
    if manifest_path.exists() and not overwrite:
        existing = _load_manifest(manifest_path)
        print(f"Manifest exists: {manifest_path} ({len(existing.get('entries', []))} entries)")
        return existing

    manifest = build_manifest_from_resolved(resolved_dir)
    _save_manifest(manifest_path, manifest)
    print(f"Wrote approval manifest: {manifest_path} ({len(manifest['entries'])} entries)")
    return manifest


def set_entry_status(
    manifest: dict[str, Any],
    *,
    semantic_key: str,
    status: str,
    reviewer: str | None = None,
    notes: str | None = None,
) -> None:
    if status not in {"pending", "approved", "rejected"}:
        raise ValueError(f"Invalid status: {status}")

    for entry in manifest.get("entries", []):
        if entry.get("semantic_key") == semantic_key:
            entry["status"] = status
            if reviewer is not None:
                entry["reviewer"] = reviewer
            if notes is not None:
                entry["notes"] = notes
            entry["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            return
    raise KeyError(f"semantic_key not found in manifest: {semantic_key}")


def approved_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in manifest.get("entries", []) if e.get("status") == "approved"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage approve/reject manifest for agent-proposals-resolved."
    )
    parser.add_argument(
        "--manifest",
        default="artifacts/agent-proposals-resolved/approval-manifest.json",
        help="Path to approval manifest JSON.",
    )
    parser.add_argument(
        "--resolved-dir",
        default="artifacts/agent-proposals-resolved",
        help="Directory of resolved proposal JSON files (for init).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create or refresh manifest from resolved/*.json")
    init_p.add_argument("--overwrite", action="store_true", help="Replace existing manifest.")

    approve_p = sub.add_parser("approve", help="Approve one semantic key.")
    approve_p.add_argument("--key", required=True)
    approve_p.add_argument("--reviewer", default=None)
    approve_p.add_argument("--notes", default="")

    reject_p = sub.add_parser("reject", help="Reject one semantic key.")
    reject_p.add_argument("--key", required=True)
    reject_p.add_argument("--reviewer", default=None)
    reject_p.add_argument("--notes", default="")

    sub.add_parser("show", help="Print manifest summary.")

    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    resolved_dir = Path(args.resolved_dir)

    if args.command == "init":
        init_manifest(resolved_dir=resolved_dir, manifest_path=manifest_path, overwrite=args.overwrite)
        return 0

    manifest = _load_manifest(manifest_path)

    if args.command == "approve":
        set_entry_status(
            manifest,
            semantic_key=args.key,
            status="approved",
            reviewer=args.reviewer,
            notes=args.notes or None,
        )
        _save_manifest(manifest_path, manifest)
        print(f"Approved: {args.key}")
        return 0

    if args.command == "reject":
        set_entry_status(
            manifest,
            semantic_key=args.key,
            status="rejected",
            reviewer=args.reviewer,
            notes=args.notes or None,
        )
        _save_manifest(manifest_path, manifest)
        print(f"Rejected: {args.key}")
        return 0

    if args.command == "show":
        for entry in manifest.get("entries", []):
            print(
                f"- {entry.get('semantic_key')}: {entry.get('status')} "
                f"(validation_passed={entry.get('validation_passed')})"
            )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
