#!/usr/bin/env bash
# Enable optional auto-conversion of raw Playwright tests before pytest runs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env.healing"

cat >"$ENV_FILE" <<'EOF'
# Sourced by scripts/run_pytest_with_auto_convert.sh (or your shell).
# When set, pytest converts raw Playwright tests to smart.* before running.
export HEALING_AUTO_CONVERT=1
EOF

chmod +x "${ROOT}/scripts/run_pytest_with_auto_convert.sh" 2>/dev/null || true

echo "Wrote ${ENV_FILE}"
echo ""
echo "Usage:"
echo "  # One-shot: convert all policy-violating tests, then run pytest"
echo "  python -m healing.convert_to_smart --scan-tests --apply"
echo "  pytest"
echo ""
echo "  # Auto-convert on every pytest run (dev only):"
echo "  source ${ENV_FILE}"
echo "  pytest   # or: ./scripts/run_pytest_with_auto_convert.sh"
echo ""
echo "  # Explicit pytest flag (no env var):"
echo "  pytest --healing-auto-convert"
