#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
TARGET_DIR="$HOME/.cryptobot"
TARGET_FILE="$TARGET_DIR/.env"

mkdir -p "$TARGET_DIR"

if [ -f "$TARGET_FILE" ]; then
  echo "~/.cryptobot/.env already exists. Skipping creation."
  exit 0
fi

if [ -f "$ROOT_DIR/env.example" ]; then
  cp "$ROOT_DIR/env.example" "$TARGET_FILE"
  echo "Created $TARGET_FILE from env.example. Please edit and fill your secrets."
else
  cat > "$TARGET_FILE" <<'EOF'
# ~/.cryptobot/.env created. Fill your secrets below.
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=
LLM_MIN_COOLDOWN_SEC=300
LLM_MIN_ATR_RATIO=0.0015
EXCHANGE_API_KEY=
EXCHANGE_API_SECRET=
HYPERLIQUID_WALLET_ADDRESS=
HYPERLIQUID_TESTNET_PRIVATE_KEY=
HYPERLIQUID_LIVE_PRIVATE_KEY=
HYPERLIQUID_TESTNET_URL=https://api.hyperliquid-testnet.xyz
HYPERLIQUID_LIVE_URL=https://api.hyperliquid.xyz
EOF
  echo "Created $TARGET_FILE with defaults. Please edit and fill your secrets."
fi


