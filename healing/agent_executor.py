"""Phase C: execute agent prompts and produce validated resolved proposals."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from healing.proposal_validation import validate_proposal_patch
from healing.resolved_apply import extract_proposal


class PromptExecutor(Protocol):
    name: str

    def execute(self, *, prompt_file: Path, workspace: Path) -> dict[str, Any]:
        """Return a LocatorPatchResult-shaped proposal dict."""


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _parse_semantic_key_from_prompt_filename(path: Path) -> str | None:
    parts = path.stem.split("__")
    if len(parts) >= 3:
        return parts[2].replace("_", ".")
    return None


def _index_agent_proposals(proposals_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not proposals_dir.exists():
        return index
    for bundle_path in sorted(proposals_dir.glob("*.json")):
        if bundle_path.name.startswith("."):
            continue
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        for proposal in bundle.get("proposals", []):
            prompt_file = proposal.get("prompt_file")
            if prompt_file:
                index[str(Path(prompt_file).resolve())] = proposal
                index[prompt_file] = proposal
    return index


def _index_mcp_proposals(proposals_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not proposals_dir.exists():
        return index
    for path in sorted(proposals_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        proposal = data.get("proposal") or data.get("bundle", {}).get("proposal")
        if not isinstance(proposal, dict):
            continue
        semantic_key = proposal.get("semantic_key")
        if semantic_key:
            index[semantic_key] = proposal
    return index


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class InternalStubExecutor:
    """Uses draft proposals from agent_runner / mcp_repair_pipeline (no live agent)."""

    name = "internal_stub"

    def __init__(self, *, agent_proposals_dir: Path, mcp_proposals_dir: Path):
        self._agent_index = _index_agent_proposals(agent_proposals_dir)
        self._mcp_index = _index_mcp_proposals(mcp_proposals_dir)

    def execute(self, *, prompt_file: Path, workspace: Path) -> dict[str, Any]:
        resolved = str(prompt_file.resolve())
        if resolved in self._agent_index:
            return dict(self._agent_index[resolved])
        if str(prompt_file) in self._agent_index:
            return dict(self._agent_index[str(prompt_file)])

        semantic_key = _parse_semantic_key_from_prompt_filename(prompt_file)
        if semantic_key and semantic_key in self._mcp_index:
            return dict(self._mcp_index[semantic_key])

        content = prompt_file.read_text(encoding="utf-8")
        match = re.search(r"semantic_key:\s*`([^`]+)`", content)
        if match and match.group(1) in self._mcp_index:
            return dict(self._mcp_index[match.group(1)])

        raise ValueError(
            f"No draft proposal found for prompt {prompt_file}. "
            "Run agent_runner or mcp_repair_pipeline first, or use --executor cursor_sdk."
        )


class CursorSdkExecutor:
    """Run prompt via Cursor SDK Agent.prompt (requires cursor-sdk + CURSOR_API_KEY)."""

    name = "cursor_sdk"

    def __init__(self, *, workspace: Path, model: str = "composer-2.5"):
        self._workspace = workspace
        self._model = model

    def execute(self, *, prompt_file: Path, workspace: Path) -> dict[str, Any]:
        api_key = os.environ.get("CURSOR_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("CURSOR_API_KEY is required for cursor_sdk executor.")

        try:
            from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
        except ImportError as exc:
            raise RuntimeError(
                "cursor-sdk is not installed. pip install cursor-sdk or use --executor internal_stub."
            ) from exc

        prompt_body = prompt_file.read_text(encoding="utf-8")
        instruction = (
            f"{prompt_body}\n\n"
            "Return ONLY a single JSON object shaped like LocatorPatchResult with fields: "
            "classification, patch_type, semantic_key, confidence, reason, files_changed, "
            "validation_command, patch (YAML string for locator_registry.yaml)."
        )

        result = Agent.prompt(
            instruction,
            AgentOptions(
                api_key=api_key,
                model=self._model,
                local=LocalAgentOptions(cwd=str(workspace)),
            ),
        )
        if getattr(result, "status", None) == "error":
            raise RuntimeError(f"Cursor SDK agent run failed: {getattr(result, 'result', result)}")

        text = getattr(result, "result", "") or ""
        parsed = _extract_json_from_text(str(text))
        if not parsed:
            raise ValueError("Cursor SDK response did not contain parseable LocatorPatchResult JSON.")
        return parsed


def select_executor(
    name: str,
    *,
    workspace: Path,
    agent_proposals_dir: Path,
    mcp_proposals_dir: Path,
    model: str,
) -> PromptExecutor:
    if name == "auto":
        if os.environ.get("CURSOR_API_KEY", "").strip():
            try:
                import cursor_sdk  # noqa: F401

                return CursorSdkExecutor(workspace=workspace, model=model)
            except ImportError:
                pass
        return InternalStubExecutor(
            agent_proposals_dir=agent_proposals_dir,
            mcp_proposals_dir=mcp_proposals_dir,
        )
    if name == "cursor_sdk":
        return CursorSdkExecutor(workspace=workspace, model=model)
    if name == "internal_stub":
        return InternalStubExecutor(
            agent_proposals_dir=agent_proposals_dir,
            mcp_proposals_dir=mcp_proposals_dir,
        )
    raise ValueError(f"Unknown executor: {name}")


def execute_prompt_file(
    *,
    prompt_file: Path,
    workspace: Path,
    resolved_dir: Path,
    executor: PromptExecutor,
    registry_path: Path,
    validate: bool,
    timeout_seconds: int,
) -> Path:
    proposal = executor.execute(prompt_file=prompt_file, workspace=workspace)
    semantic_key = proposal.get("semantic_key") or _parse_semantic_key_from_prompt_filename(
        prompt_file
    )
    if not semantic_key:
        raise ValueError(f"Could not determine semantic_key for {prompt_file}")

    payload: dict[str, Any] = {
        "prompt_file": str(prompt_file.resolve()),
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "executor": executor.name,
        "proposal": proposal,
    }

    if validate and proposal.get("patch_type") != "no_patch":
        validation = validate_proposal_patch(
            payload=payload,
            workspace=workspace,
            registry_path=registry_path,
            timeout_seconds=timeout_seconds,
        )
        payload["validation"] = validation.to_dict()
        proposal["validation"] = validation.to_dict()

    slug = _slug(semantic_key.replace(".", "_"))
    out_path = resolved_dir / f"{slug}.json"
    out_path.write_text(_json_dump(payload), encoding="utf-8")
    return out_path


def run_agent_executor(
    *,
    workspace: Path,
    prompts_dir: Path,
    resolved_dir: Path,
    agent_proposals_dir: Path,
    mcp_proposals_dir: Path,
    registry_path: Path,
    executor_name: str,
    model: str,
    validate: bool,
    timeout_seconds: int,
    prompt_glob: str,
) -> list[Path]:
    prompts_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir.mkdir(parents=True, exist_ok=True)

    executor = select_executor(
        executor_name,
        workspace=workspace,
        agent_proposals_dir=agent_proposals_dir,
        mcp_proposals_dir=mcp_proposals_dir,
        model=model,
    )

    written: list[Path] = []
    prompt_files = sorted(prompts_dir.glob(prompt_glob))
    if not prompt_files:
        print(f"No prompts found in {prompts_dir} ({prompt_glob})")
        return written

    for prompt_file in prompt_files:
        try:
            out_path = execute_prompt_file(
                prompt_file=prompt_file,
                workspace=workspace,
                resolved_dir=resolved_dir,
                executor=executor,
                registry_path=registry_path,
                validate=validate,
                timeout_seconds=timeout_seconds,
            )
            proposal = extract_proposal(json.loads(out_path.read_text(encoding="utf-8")))
            validation = proposal.get("validation") or {}
            status = "passed" if validation.get("passed") else (
                "skipped" if not validate else "failed"
            )
            print(f"[ok] {proposal.get('semantic_key')}: {out_path.name} validation={status}")
            written.append(out_path)
        except Exception as exc:
            print(f"[error] {prompt_file.name}: {exc}")

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase C: execute agent prompt markdown files and write validated resolved "
            "proposals to artifacts/agent-proposals-resolved/."
        )
    )
    parser.add_argument("--workspace", default=".", help="Workspace root.")
    parser.add_argument(
        "--prompts-dir",
        default="artifacts/agent-prompts",
        help="Directory of agent prompt markdown files.",
    )
    parser.add_argument(
        "--resolved-dir",
        default="artifacts/agent-proposals-resolved",
        help="Output directory for resolved proposal JSON.",
    )
    parser.add_argument(
        "--agent-proposals-dir",
        default="artifacts/agent-proposals",
        help="Draft proposals from agent_runner (internal_stub source).",
    )
    parser.add_argument(
        "--mcp-proposals-dir",
        default="artifacts/mcp-repair-bundles/proposals",
        help="MCP bundle proposals (internal_stub fallback source).",
    )
    parser.add_argument("--registry", default="locator_registry.yaml")
    parser.add_argument(
        "--executor",
        choices=("auto", "internal_stub", "cursor_sdk"),
        default="auto",
        help="auto: cursor_sdk when CURSOR_API_KEY set, else internal_stub.",
    )
    parser.add_argument("--model", default="composer-2.5", help="Cursor SDK model id.")
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip running validation_command against patched registry copy.",
    )
    parser.add_argument("--timeout", type=int, default=300, help="Validation timeout seconds.")
    parser.add_argument(
        "--glob",
        default="*.md",
        dest="prompt_glob",
        help="Glob for prompt files within prompts-dir.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    written = run_agent_executor(
        workspace=workspace,
        prompts_dir=(workspace / args.prompts_dir).resolve(),
        resolved_dir=(workspace / args.resolved_dir).resolve(),
        agent_proposals_dir=(workspace / args.agent_proposals_dir).resolve(),
        mcp_proposals_dir=(workspace / args.mcp_proposals_dir).resolve(),
        registry_path=(workspace / args.registry).resolve(),
        executor_name=args.executor,
        model=args.model,
        validate=not args.no_validate,
        timeout_seconds=args.timeout,
        prompt_glob=args.prompt_glob,
    )
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
