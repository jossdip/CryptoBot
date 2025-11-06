#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

echo "[update_ci] Updating repository to origin/main"
git fetch --all
git reset --hard origin/main

echo "[update_ci] Ensuring virtualenv and dependencies"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip -q install -U pip || true
if [[ -f requirements.txt ]]; then
  pip -q install -r requirements.txt || true
fi

echo "[update_ci] Restarting bot only if running"
bash ./deploy/restart_if_running.sh || true

echo "[update_ci] Done"


