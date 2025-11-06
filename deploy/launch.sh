#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./deploy/launch.sh <command> [args...]
# Example:
#   ./deploy/launch.sh cryptobot-live --config configs/live.frugal.yaml --provider ccxt --exchange binance
#   ./deploy/launch.sh cryptobot-live-hl --config configs/live.hyperliquid.yaml
#
# Notes:
# - Runs the bot inside a tmux session for resiliency (default session name: cryptobot)
# - Persists the exact command to .run_cmd and the session name to .run_session for future restarts

SESSION_NAME=${SESSION_NAME:-cryptobot}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Provide the command to run, e.g.:" >&2
  echo "  ./deploy/launch.sh cryptobot-live --config configs/live.frugal.yaml" >&2
  exit 1
fi

CMD="$*"

cd "$REPO_DIR"

# Ensure venv exists and deps are installed
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip -q install -U pip || true
if [[ -f requirements.txt ]]; then
  pip -q install -r requirements.txt || true
fi

# Persist run metadata
echo "$CMD" > .run_cmd
echo "$SESSION_NAME" > .run_session

# Start (or restart) tmux session
if command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux kill-session -t "$SESSION_NAME"
  fi
  tmux new-session -d -s "$SESSION_NAME" "bash -lc 'cd $REPO_DIR && source .venv/bin/activate && exec $CMD'"
  echo "Started in tmux session: $SESSION_NAME"
  echo "Attach: tmux attach -t $SESSION_NAME"
else
  # Fallback: run in background (less resilient than tmux)
  nohup bash -lc "cd $REPO_DIR && source .venv/bin/activate && exec $CMD" >/tmp/cryptobot.out 2>&1 &
  echo $! > .run_pid
  echo "Started in background (tmux not found). PID: $(cat .run_pid)"
fi


