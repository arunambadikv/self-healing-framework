from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .exceptions import RegistryValidationError

ALLOWED_ACTIONS = {
    "click",
    "fill",
    "check",
    "uncheck",
    "select_option",
    "expect_visible",
    "expect_text",
    "drag_to",
    "drag",
    "drop",
}

ALLOWED_LOCATOR_TYPES = {
    "test_id",
    "role",
    "label",
    "text",
    "placeholder",
    "css",
    "frame_css",
}

REQUIRED_CANDIDATE_FIELDS: dict[str, tuple[str, ...]] = {
    "test_id": ("value",),
    "role": ("role",),
    "label": ("value",),
    "text": ("value",),
    "placeholder": ("value",),
    "css": ("value",),
    "frame_css": ("frame", "value"),
}

BROAD_CSS_VALUES = {
    "*",
    "a",
    "button",
    "div",
    "input",
    "label",
    "meter",
    "p",
    "select",
    "span",
    "textarea",
}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_candidate(candidate: Any, key: str, phase: str, index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return [f"{key}.{phase}[{index}] must be a mapping."]

    candidate_type = candidate.get("type")
    if candidate_type not in ALLOWED_LOCATOR_TYPES:
        errors.append(
            f"{key}.{phase}[{index}] has unsupported locator type '{candidate_type}'."
        )
        return errors

    required_fields = REQUIRED_CANDIDATE_FIELDS[candidate_type]
    for field_name in required_fields:
        if not _is_non_empty_string(candidate.get(field_name)):
            errors.append(
                f"{key}.{phase}[{index}] missing non-empty '{field_name}' "
                f"for locator type '{candidate_type}'."
            )

    return errors


def validate_registry(registry: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(registry, dict):
        return ["Registry root must be a mapping of semantic keys to entries."]

    for key, entry in registry.items():
        if not _is_non_empty_string(key):
            errors.append("Registry contains an empty semantic key.")
            continue
        if not isinstance(entry, dict):
            errors.append(f"{key} entry must be a mapping.")
            continue

        if not _is_non_empty_string(entry.get("intent")):
            errors.append(f"{key}.intent must be a non-empty string.")

        action = entry.get("action")
        if not _is_non_empty_string(action):
            errors.append(f"{key}.action must be a non-empty string.")
        elif action not in ALLOWED_ACTIONS:
            errors.append(
                f"{key}.action '{action}' is unsupported. "
                f"Allowed: {sorted(ALLOWED_ACTIONS)}."
            )

        preferred = entry.get("preferred")
        fallback = entry.get("fallback")
        if not isinstance(preferred, list) or not preferred:
            errors.append(f"{key}.preferred must be a non-empty list.")
            preferred = preferred if isinstance(preferred, list) else []
        if fallback is None:
            fallback = []
        if not isinstance(fallback, list):
            errors.append(f"{key}.fallback must be a list.")
            fallback = []
        if not preferred and not fallback:
            errors.append(
                f"{key} must define at least one locator candidate in preferred/fallback."
            )

        for index, candidate in enumerate(preferred):
            errors.extend(_validate_candidate(candidate, key, "preferred", index))
        for index, candidate in enumerate(fallback):
            errors.extend(_validate_candidate(candidate, key, "fallback", index))

        seen: set[str] = set()
        for phase, candidates in (("preferred", preferred), ("fallback", fallback)):
            for index, candidate in enumerate(candidates):
                if not isinstance(candidate, dict):
                    continue
                signature = str(sorted(candidate.items()))
                if signature in seen:
                    errors.append(
                        f"{key}.{phase}[{index}] duplicates an earlier locator candidate."
                    )
                seen.add(signature)

    return errors


def lint_registry(registry: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for key, entry in registry.items():
        preferred = entry.get("preferred", [])
        for index, candidate in enumerate(preferred):
            if not isinstance(candidate, dict):
                continue
            if candidate.get("type") == "css":
                css_value = str(candidate.get("value", "")).strip()
                if css_value in BROAD_CSS_VALUES:
                    warnings.append(
                        f"{key}.preferred[{index}] uses very broad CSS '{css_value}'. "
                        "Prefer test_id/role/label/placeholder/text when possible."
                    )
            if candidate.get("type") == "role" and not _is_non_empty_string(
                candidate.get("name")
            ):
                warnings.append(
                    f"{key}.preferred[{index}] uses role locator without a name. "
                    "This may match multiple elements."
                )
    return warnings


def load_registry(filepath: str) -> dict[str, Any]:
    registry = yaml.safe_load(Path(filepath).read_text(encoding="utf-8"))
    errors = validate_registry(registry)
    if errors:
        raise RegistryValidationError(
            "Invalid locator registry:\n- " + "\n- ".join(errors)
        )
    return registry
