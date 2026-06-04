from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RegistryPatchSuggestion:
    semantic_key: str
    change_type: str
    confidence: float
    reason: str
    current_candidate: dict[str, Any] | None
    suggested_candidate: dict[str, Any] | None


@dataclass
class LocatorPatchResult:
    classification: str
    patch_type: str
    semantic_key: str | None
    confidence: float
    reason: str
    files_changed: list[str]
    validation_command: str
    patch: str
