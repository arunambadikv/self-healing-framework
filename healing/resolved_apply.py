"""Apply resolved agent/MCP proposal payloads to the locator registry."""

from __future__ import annotations

from typing import Any

import yaml

from healing.apply_suggestion import _apply_add_semantic_key, _apply_promote_fallback


def extract_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    proposal = payload.get("proposal")
    if isinstance(proposal, dict):
        return proposal
    if isinstance(payload, dict) and payload.get("semantic_key"):
        return payload
    raise ValueError("Resolved payload missing proposal or semantic_key.")


def apply_proposal_to_registry(registry: dict[str, Any], payload: dict[str, Any]) -> str:
    proposal = extract_proposal(payload)
    semantic_key = proposal.get("semantic_key")
    if not semantic_key:
        raise ValueError("Proposal missing semantic_key.")

    change_type = payload.get("change_type") or payload.get("source_change_type")
    patch_type = proposal.get("patch_type")
    patch_text = proposal.get("patch", "")

    if (
        change_type in {"promote_fallback", "registry_only"}
        or patch_type == "registry_only"
    ) and proposal.get("suggested_candidate"):
        return _apply_promote_fallback(
            registry, semantic_key, proposal["suggested_candidate"]
        )

    if patch_text and "semantic_key" not in patch_text:
        parsed = yaml.safe_load(patch_text)
        if isinstance(parsed, dict) and semantic_key in parsed:
            if semantic_key in registry:
                registry[semantic_key] = parsed[semantic_key]
                return f"Updated existing key '{semantic_key}' from agent patch YAML."
            return _apply_add_semantic_key(registry, semantic_key, parsed[semantic_key])

    if patch_type == "no_patch":
        raise ValueError(f"Proposal for '{semantic_key}' is no_patch; nothing to apply.")

    raise ValueError(
        f"Could not apply proposal for '{semantic_key}'. "
        "Expected YAML patch or suggested_candidate."
    )
