#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# Determine session name and command
SESSION_NAME="cryptobot"
if [[ -f .run_session ]]; then
  SESSION_NAME=$(cat .run_session)
fi

# Prefer saved command when available (launched via deploy/launch.sh)
if [[ -f .run_cmd ]]; then
  CMD=$(cat .run_cmd)

  # Reinstall deps (caller should have done it, but safe to keep minimal)
  if [[ -d .venv ]]; then
    source .venv/bin/activate
    if [[ -f requirements.txt ]]; then
      pip -q install -r requirements.txt || true
    fi
  fi

  # If running in tmux session, restart it; else, if background pid exists, restart
  if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux kill-session -t "$SESSION_NAME"
    tmux new-session -d -s "$SESSION_NAME" "bash -lc 'cd $REPO_DIR && source .venv/bin/activate && exec $CMD'"
    echo "Restarted tmux session: $SESSION_NAME"
    exit 0
  fi

  # Fallback: background pid
  if [[ -f .run_pid ]]; then
    PID=$(cat .run_pid)
    if ps -p "$PID" >/dev/null 2>&1; then
      kill "$PID" || true
      sleep 1
    fi
    nohup bash -lc "cd $REPO_DIR && source .venv/bin/activate && exec $CMD" >/tmp/cryptobot.out 2>&1 &
    echo $! > .run_pid
    echo "Restarted background process. New PID: $(cat .run_pid)"
    exit 0
  fi
fi

# No saved command: detect running process started externally (e.g., from your interface)
pattern='cryptobot-live-hl|cryptobot-live|cryptobot\.cli\.live_hyperliquid|cryptobot\.cli\.live'
if command -v pgrep >/dev/null 2>&1 && command -v ps >/dev/null 2>&1; then
  PID=$(pgrep -fo "$pattern" || true)
  if [[ -n "${PID:-}" ]]; then
    CMD=$(ps -p "$PID" -o args=)
    # Graceful stop
    kill "$PID" || true
    sleep 2
    if ps -p "$PID" >/dev/null 2>&1; then
      kill -9 "$PID" || true
    fi
    # Relaunch with same command line, within repo venv
    if [[ -d .venv ]]; then
      source .venv/bin/activate
    fi
    nohup bash -lc "cd $REPO_DIR && source .venv/bin/activate 2>/dev/null || true; exec $CMD" >/tmp/cryptobot.out 2>&1 &
    echo $! > .run_pid
    echo "$CMD" > .run_cmd
    echo "$SESSION_NAME" > .run_session
    echo "Restarted external process (reused original command). New PID: $(cat .run_pid)"
    exit 0
  fi
fi

echo "Bot not running. Skipping restart."


