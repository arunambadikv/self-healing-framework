"""Unit tests for Phase C agent executor and approval manifest."""

import json
from pathlib import Path

from healing.approval_manifest import build_manifest_from_resolved, set_entry_status
from healing.resolved_apply import apply_proposal_to_registry, extract_proposal


def test_apply_yaml_patch_from_resolved_payload():
    registry = {
        "demo.sample": {
            "intent": "old",
            "action": "click",
            "preferred": [{"type": "css", "value": "#old"}],
            "fallback": [],
        }
    }
    payload = {
        "proposal": {
            "semantic_key": "demo.sample",
            "patch_type": "registry_only",
            "patch": (
                "demo.sample:\n  intent: updated\n  action: click\n  preferred:\n"
                "  - type: role\n    role: button\n    name: Go\n  fallback: []\n"
            ),
        }
    }
    message = apply_proposal_to_registry(registry, payload)
    assert "Updated" in message
    assert registry["demo.sample"]["intent"] == "updated"


def test_build_manifest_from_resolved(tmp_path: Path):
    resolved = tmp_path / "demo_sample.json"
    resolved.write_text(
        json.dumps(
            {
                "proposal": {
                    "semantic_key": "demo.sample",
                    "validation_command": "pytest -q",
                    "patch_type": "registry_only",
                    "patch": "demo.sample:\n  action: click\n  preferred: []\n  fallback: []\n",
                },
                "validation": {"passed": True, "command": "pytest -q", "exit_code": 0},
            }
        ),
        encoding="utf-8",
    )
    manifest = build_manifest_from_resolved(tmp_path)
    assert len(manifest["entries"]) == 1
    assert manifest["entries"][0]["semantic_key"] == "demo.sample"
    assert manifest["entries"][0]["validation_passed"] is True


def test_set_entry_status_approve():
    manifest = {
        "entries": [
            {"semantic_key": "demo.sample", "status": "pending"},
        ]
    }
    set_entry_status(manifest, semantic_key="demo.sample", status="approved", reviewer="ci")
    assert manifest["entries"][0]["status"] == "approved"
    assert manifest["entries"][0]["reviewer"] == "ci"
