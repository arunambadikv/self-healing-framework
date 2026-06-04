#!/usr/bin/env bash
# Phase C: agent_runner → executor → approval manifest → apply (approved only).
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

EXECUTOR="${EXECUTOR:-auto}"
VALIDATE="${VALIDATE:-1}"
APPLY="${APPLY:-0}"

echo "== Phase A: generate agent prompts + draft proposals =="
"$PYTHON" -m healing.agent_runner --all

echo ""
echo "== Phase C: execute prompts → agent-proposals-resolved =="
EXEC_ARGS=(--executor "$EXECUTOR")
if [[ "$VALIDATE" == "0" ]]; then
  EXEC_ARGS+=(--no-validate)
fi
"$PYTHON" -m healing.agent_executor "${EXEC_ARGS[@]}"

echo ""
echo "== Approval manifest =="
"$PYTHON" -m healing.approval_manifest init --overwrite

echo ""
echo "Pending approvals:"
"$PYTHON" -m healing.approval_manifest show

cat <<'EOF'

Next steps (human):
  python -m healing.approval_manifest approve --key <semantic_key>
  python -m healing.agent_apply --apply

Or with Cursor SDK executor:
  export CURSOR_API_KEY=...
  EXECUTOR=cursor_sdk bash scripts/run_agent_phase_c.sh

EOF

if [[ "$APPLY" == "1" ]]; then
  echo "== Apply approved (requires prior approve commands) =="
  "$PYTHON" -m healing.agent_apply --apply
fi
