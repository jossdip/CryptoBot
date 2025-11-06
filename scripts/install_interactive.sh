#!/usr/bin/env bash
set -euo pipefail

echo "Installing CryptoBot interactive CLI entrypoints..."

if ! command -v python &>/dev/null; then
  echo "python not found in PATH" >&2
  exit 1
fi

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  echo "Detected virtualenv: $VIRTUAL_ENV"
  echo "Installing package in editable mode into venv (pip install -e .)"
  python -m pip install -e .
else
  echo "No virtualenv detected. Installing for current user (pip install --user -e .)"
  python -m pip install --user -e .
  BIN_DIR="$HOME/.local/bin"
  if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "\n[Hint] Add $BIN_DIR to your PATH to use 'cryptobot'/'cb' without activating a venv:"
    echo "  echo 'export PATH=\"$BIN_DIR:$PATH\"' >> ~/.bashrc && source ~/.bashrc"
  fi
fi

echo -e "Done. You can run:\n  - cryptobot\n  - cb"


