from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from healing.patch_models import RegistryPatchSuggestion


def load_healing_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def suggest_registry_updates(report_path: str | Path) -> list[RegistryPatchSuggestion]:
    report = load_healing_report(report_path)
    suggestions: list[RegistryPatchSuggestion] = []

    for event in report.get("events", []):
        if event.get("status") == "healed":
            used_candidate = event.get("used_candidate")
            suggestions.append(
                RegistryPatchSuggestion(
                    semantic_key=event["key"],
                    change_type="promote_fallback",
                    confidence=0.8,
                    reason=(
                        "A fallback locator successfully completed the action. "
                        "Review and consider promoting it to preferred if it is stable and specific."
                    ),
                    current_candidate=None,
                    suggested_candidate=used_candidate,
                )
            )
            continue

        details = event.get("details", {})
        if details.get("classification") == "missing_key":
            suggestions.append(
                RegistryPatchSuggestion(
                    semantic_key=event["key"],
                    change_type="add_semantic_key",
                    confidence=0.6,
                    reason=(
                        "A semantic key was used in a test but not found in locator_registry.yaml. "
                        "Add this key before rerunning."
                    ),
                    current_candidate=None,
                    suggested_candidate=details.get("suggested_registry_entry"),
                )
            )

    return suggestions
