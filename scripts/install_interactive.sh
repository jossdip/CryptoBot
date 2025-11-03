#!/usr/bin/env bash
set -euo pipefail

echo "Installing CryptoBot interactive CLI entrypoints..."

if ! command -v python &>/dev/null; then
  echo "python not found in PATH" >&2
  exit 1
fi

echo "Installing package in editable mode (pip install -e .)"
python -m pip install -e .

echo "Done. You can run:\n  - cryptobot\n  - cb"


