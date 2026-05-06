#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtual environment at $PROJECT_DIR/.venv" >&2
  echo "Run: uv sync" >&2
  exit 1
fi

# Use the venv's interpreter directly to avoid stale entry points.
exec "$VENV_PYTHON" -m labelme "$@"
