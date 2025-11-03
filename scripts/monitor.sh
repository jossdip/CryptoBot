#!/bin/bash
set -euo pipefail

SERVICE_NAME="cryptobot-hyperliquid"

echo "[monitor] Checking service: ${SERVICE_NAME}"
if systemctl is-active --quiet "${SERVICE_NAME}"; then
  echo "[monitor] Service is running."
else
  echo "[monitor] Service is not running. Attempting restart..." >&2
  systemctl restart "${SERVICE_NAME}" || true
fi


