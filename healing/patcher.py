from __future__ import annotations

import json
from pathlib import Path

from healing.registry_updater import suggest_registry_updates


def generate_registry_patch_markdown(report_path: str | Path, output_path: str | Path) -> None:
    suggestions = suggest_registry_updates(report_path)

    lines = [
        "# Registry Patch Suggestions",
        "",
        "Review these suggestions before applying them.",
        "",
    ]

    if not suggestions:
        lines.append("No healed or missing-key suggestions found in the report.")
    else:
        for item in suggestions:
            lines.extend(
                [
                    f"## {item.semantic_key}",
                    "",
                    f"- change type: `{item.change_type}`",
                    f"- confidence: `{item.confidence}`",
                    f"- reason: {item.reason}",
                    "- suggested candidate:",
                    "```json",
                    json.dumps(item.suggested_candidate, indent=2),
                    "```",
                    "",
                ]
            )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
