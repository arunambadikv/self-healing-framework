class HealingError(Exception):
    pass


class RegistryValidationError(HealingError):
    pass


class LocatorKeyNotFoundError(HealingError):
    pass


class ActionMismatchError(HealingError):
    pass


class AllLocatorCandidatesFailedError(HealingError):
    def __init__(
        self,
        *,
        key: str,
        action: str,
        intent: str,
        attempted_candidates: list[dict],
        candidate_errors: list[dict],
        last_error: Exception | None,
    ) -> None:
        message_lines = [
            f"All locator candidates failed for key '{key}'.",
            f"Action: {action}",
            f"Intent: {intent}",
            f"Candidates attempted: {attempted_candidates}",
        ]
        if candidate_errors:
            message_lines.append("Candidate failures:")
            for item in candidate_errors:
                message_lines.append(
                    "  - "
                    f"#{item.get('index')} [{item.get('phase')}]: "
                    f"{item.get('candidate')} -> {item.get('error_type')}: {item.get('error')}"
                )
        message_lines.append(f"Last error: {last_error}")
        super().__init__("\n".join(message_lines))
