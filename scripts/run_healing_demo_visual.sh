#!/usr/bin/env bash
# Run healing demo tests in a visible browser (headed + slow-mo).
set -euo pipefail
cd "$(dirname "$0")/.."

SLOW_MO="${HEALING_DEMO_SLOW_MO:-400}"
export HEALING_DEMO_SLOW_MO="$SLOW_MO"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

exec pytest tests/test_orangehrm_healing.py --run-healing-demo -v "$@"
