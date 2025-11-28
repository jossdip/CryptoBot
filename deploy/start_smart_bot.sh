#!/usr/bin/env bash
set -e

# Wrapper to start the Smart Breakout Bot using the standard deployment launcher
# This ensures it runs in tmux/background as per standard deployment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Starting Smart Breakout Bot..."
# Use the launch.sh script to run the module
# We pass --config configs/live.hyperliquid.yaml by default
"$SCRIPT_DIR/launch.sh" python3 -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml "$@"

