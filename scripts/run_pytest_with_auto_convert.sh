#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "${ROOT}/.env.healing" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/.env.healing"
fi

export HEALING_AUTO_CONVERT="${HEALING_AUTO_CONVERT:-1}"
PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

exec "$PYTHON" -m pytest "$@"
