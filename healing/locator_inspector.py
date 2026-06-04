from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from healing.locator_builder import build_locator


@dataclass
class CandidateProbeResult:
    candidate: dict[str, Any]
    count: int
    visible: bool
    attached: bool
    error: str | None = None


@dataclass
class InspectionResult:
    semantic_key: str
    base_url: str
    probes: list[CandidateProbeResult] = field(default_factory=list)
    accessibility_hint: str | None = None


def probe_registry_candidates(
    page: Any,
    *,
    semantic_key: str,
    registry_entry: dict[str, Any],
    base_url: str,
) -> InspectionResult:
    """Probe preferred/fallback candidates with Playwright (MCP-equivalent inspection)."""
    result = InspectionResult(semantic_key=semantic_key, base_url=base_url)
    candidates = list(registry_entry.get("preferred", [])) + list(
        registry_entry.get("fallback", [])
    )

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            locator = build_locator(page, candidate)
            count = locator.count()
            visible = False
            attached = False
            if count > 0:
                first = locator.first
                try:
                    first.wait_for(state="attached", timeout=2000)
                    attached = True
                except Exception:
                    attached = False
                try:
                    visible = first.is_visible()
                except Exception:
                    visible = False
            result.probes.append(
                CandidateProbeResult(
                    candidate=candidate,
                    count=count,
                    visible=visible,
                    attached=attached,
                )
            )
        except Exception as exc:
            result.probes.append(
                CandidateProbeResult(
                    candidate=candidate,
                    count=0,
                    visible=False,
                    attached=False,
                    error=str(exc),
                )
            )

    try:
        snapshot = page.accessibility.snapshot()
        if snapshot:
            result.accessibility_hint = _summarize_accessibility(snapshot)
    except Exception as exc:
        result.accessibility_hint = f"accessibility snapshot unavailable: {exc}"

    return result


def _summarize_accessibility(node: dict[str, Any], depth: int = 0, max_depth: int = 3) -> str:
    """Compact summary of interactive roles from accessibility tree."""
    lines: list[str] = []
    role = node.get("role", "")
    name = node.get("name", "")
    if role in {"button", "link", "textbox", "combobox", "checkbox", "radio", "slider", "meter", "progressbar"}:
        if name:
            lines.append(f"{role}: {name}")
        else:
            lines.append(role)

    if depth >= max_depth:
        return "\n".join(lines[:40])

    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            child_summary = _summarize_accessibility(child, depth + 1, max_depth)
            if child_summary:
                lines.append(child_summary)

    return "\n".join(lines[:40])


def rank_working_candidates(probes: list[CandidateProbeResult]) -> list[dict[str, Any]]:
    """Return candidates that are uniquely matched and visible."""
    working = [
        p.candidate
        for p in probes
        if p.count == 1 and p.visible and not p.error
    ]
    return working
