#!/usr/bin/env bash
set -euo pipefail

echo "Installing CryptoBot interactive CLI entrypoints..."

# Pick a python executable
if command -v python3 &>/dev/null; then
  PY=python3
elif command -v python &>/dev/null; then
  PY=python
else
  echo "python not found in PATH" >&2
  exit 1
fi

# If already inside a virtualenv, install directly there
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "Detected virtualenv: $VIRTUAL_ENV"
  echo "Installing package in editable mode into venv (pip install -e .)"
  "$PY" -m pip install -e .
  echo -e "Done. You can run:\n  - cryptobot\n  - cb"
  exit 0
fi

# Always prefer a local venv to avoid PEP 668 (externally-managed) errors
VENV_DIR=".venv"
if [[ -d "$VENV_DIR" ]]; then
  echo "Found existing virtualenv at $VENV_DIR"
else
  echo "No virtualenv detected. Creating local venv at $VENV_DIR"
  if ! "$PY" -m venv "$VENV_DIR"; then
    echo "Failed to create a virtual environment." >&2
    echo "On Debian/Ubuntu/Kali-based systems, install venv support: sudo apt install python3-venv" >&2
    echo "Then re-run: bash scripts/install_interactive.sh" >&2
    exit 1
  fi
fi

# Activate the venv for the remainder of the script
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
python -m pip install --upgrade pip >/dev/null

echo "Installing package in editable mode into venv (pip install -e .)"
python -m pip install -e .

echo -e "Done. To use the CLI now:\n  - source $VENV_DIR/bin/activate\n  - cryptobot\n  - cb"


