#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy/install_service.sh [service=paper]
# Services: paper (default) or live

SERVICE=${1:-paper}
UNIT_SRC="deploy/cryptobot-${SERVICE}.service"
UNIT_DST="/etc/systemd/system/cryptobot-${SERVICE}@.service"

# Detect the real user (even when running with sudo)
# Try multiple methods: SUDO_USER, logname, or extract from $HOME
if [[ -n "${SUDO_USER:-}" ]]; then
    TARGET_USER="${SUDO_USER}"
elif command -v logname &> /dev/null; then
    TARGET_USER=$(logname 2>/dev/null || echo "${USER}")
elif [[ -n "${HOME:-}" ]]; then
    TARGET_USER=$(basename "${HOME}")
else
    TARGET_USER="${USER}"
fi

if [[ ! -f "${UNIT_SRC}" ]]; then
  echo "Service file ${UNIT_SRC} not found." >&2
  exit 1
fi

echo "Installing systemd unit for user: ${TARGET_USER} (service: ${SERVICE})"
sudo cp "${UNIT_SRC}" "${UNIT_DST}"
sudo systemctl daemon-reload
sudo systemctl enable "cryptobot-${SERVICE}@${TARGET_USER}"
sudo systemctl restart "cryptobot-${SERVICE}@${TARGET_USER}"
sudo systemctl status "cryptobot-${SERVICE}@${TARGET_USER}" --no-pager || true


