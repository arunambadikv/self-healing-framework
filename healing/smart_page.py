from playwright.sync_api import Page, expect
from .exceptions import (
    ActionMismatchError,
    AllLocatorCandidatesFailedError,
    LocatorKeyNotFoundError,
)
from .locator_builder import build_locator
from .report import HealingReport

class SmartPage:
    def __init__(self, page: Page, registry: dict, report: HealingReport):
        self.page = page
        self.registry = registry
        self.report = report

    @staticmethod
    def _missing_key_stub(key: str, action: str) -> dict:
        return {
            "intent": f"TODO: describe intent for '{key}'",
            "action": action,
            "preferred": [
                {
                    "type": "css",
                    "value": "TODO: add stable locator",
                }
            ],
            "fallback": [],
        }

    def _get_registry_entry(self, key: str, called_action: str) -> dict:
        if key not in self.registry:
            self.report.record_event(
                key=key,
                action=called_action,
                status="failed",
                used_candidate=None,
                message=f"Missing semantic key '{key}' in registry.",
                details={
                    "classification": "missing_key",
                    "suggested_registry_entry": self._missing_key_stub(
                        key=key, action=called_action
                    ),
                },
            )
            raise LocatorKeyNotFoundError(f"Key '{key}' not found in registry.")
        return self.registry[key]

    def _ensure_action_matches(
        self, key: str, called_action: str, allowed_registry_actions: set[str] | None = None
    ) -> dict:
        entry = self._get_registry_entry(key, called_action=called_action)
        configured_action = entry.get("action")
        if allowed_registry_actions is None:
            allowed_registry_actions = {called_action}
        if configured_action not in allowed_registry_actions:
            raise ActionMismatchError(
                f"Action mismatch for key '{key}': test called '{called_action}', "
                f"but registry action is '{configured_action}'. "
                f"Allowed actions for this call: {sorted(allowed_registry_actions)}."
            )
        return entry

    @staticmethod
    def _stringify_error(error: Exception) -> str:
        text = str(error).strip()
        if len(text) > 500:
            return text[:500] + "...(truncated)"
        return text

    def _execute_with_healing(self, key: str, action: str, action_func) -> None:
        entry = self._ensure_action_matches(key, action)
        intent = entry.get("intent", "No intent specified")
        preferred = entry.get("preferred", [])
        fallback = entry.get("fallback", [])
        
        candidates = preferred + fallback
        last_error = None
        candidate_errors: list[dict] = []
        
        for idx, candidate in enumerate(candidates):
            is_primary = idx < len(preferred)
            phase = "preferred" if is_primary else "fallback"
            
            try:
                locator = build_locator(self.page, candidate)
                action_func(locator)
                
                # Succeeded
                status = "primary" if is_primary else "healed"
                self.report.record_event(
                    key=key,
                    action=action,
                    status=status,
                    used_candidate=candidate,
                    message=f"{key} succeeded using {status} locator"
                )
                return
            except Exception as e:
                last_error = e
                candidate_errors.append(
                    {
                        "index": idx,
                        "phase": phase,
                        "candidate": candidate,
                        "error_type": type(e).__name__,
                        "error": self._stringify_error(e),
                    }
                )
                continue
                
        # If we reach here, all candidates failed
        self.report.record_event(
            key=key,
            action=action,
            status="failed",
            used_candidate=None,
            message=f"{key} failed all candidates",
        )
        raise AllLocatorCandidatesFailedError(
            key=key,
            action=action,
            intent=intent,
            attempted_candidates=candidates,
            candidate_errors=candidate_errors,
            last_error=last_error,
        )

    def click(self, key: str) -> None:
        self._execute_with_healing(key, "click", lambda loc: loc.click(timeout=3000))

    def fill(self, key: str, value: str) -> None:
        self._execute_with_healing(key, "fill", lambda loc: loc.fill(value, timeout=3000))

    def check(self, key: str) -> None:
        self._execute_with_healing(key, "check", lambda loc: loc.check(timeout=3000))

    def uncheck(self, key: str) -> None:
        self._execute_with_healing(key, "uncheck", lambda loc: loc.uncheck(timeout=3000))

    def select_option(self, key: str, value: str) -> None:
        self._execute_with_healing(key, "select_option", lambda loc: loc.select_option(value, timeout=3000))
        
    def expect_visible(self, key: str) -> None:
        self._execute_with_healing(key, "expect_visible", lambda loc: expect(loc).to_be_visible(timeout=3000))
        
    def expect_text(self, key: str, expected_text: str) -> None:
        self._execute_with_healing(key, "expect_text", lambda loc: expect(loc).to_have_text(expected_text, timeout=3000))
        
    def drag_to(self, source_key: str, target_key: str) -> None:
        source_loc = self._get_locator_strictly(
            source_key,
            "drag_source",
            allowed_registry_actions={"drag", "drag_to"},
        )
        target_loc = self._get_locator_strictly(
            target_key,
            "drag_target",
            allowed_registry_actions={"drop", "drag_to"},
        )
        source_loc.drag_to(target_loc, timeout=3000)
        
    def _get_locator_strictly(
        self, key: str, action: str, allowed_registry_actions: set[str] | None = None
    ):
        entry = self._ensure_action_matches(
            key, action, allowed_registry_actions=allowed_registry_actions
        )
        intent = entry.get("intent", "No intent specified")
        candidates = entry.get("preferred", []) + entry.get("fallback", [])
        last_error = None
        candidate_errors: list[dict] = []
        
        for idx, candidate in enumerate(candidates):
            try:
                locator = build_locator(self.page, candidate)
                locator.wait_for(state="attached", timeout=3000)
                is_primary = idx < len(entry.get("preferred", []))
                status = "primary" if is_primary else "healed"
                self.report.record_event(
                    key=key,
                    action=action,
                    status=status,
                    used_candidate=candidate,
                    message=f"{key} locator found using {status} locator"
                )
                return locator
            except Exception as e:
                last_error = e
                phase = "preferred" if idx < len(entry.get("preferred", [])) else "fallback"
                candidate_errors.append(
                    {
                        "index": idx,
                        "phase": phase,
                        "candidate": candidate,
                        "error_type": type(e).__name__,
                        "error": self._stringify_error(e),
                    }
                )
                continue

        raise AllLocatorCandidatesFailedError(
            key=key,
            action=action,
            intent=intent,
            attempted_candidates=candidates,
            candidate_errors=candidate_errors,
            last_error=last_error,
        )
