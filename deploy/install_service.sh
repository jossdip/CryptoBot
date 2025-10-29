#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy/install_service.sh [service=paper]
# Services: paper (default) or live

SERVICE=${1:-paper}
UNIT_SRC="deploy/cryptobot-${SERVICE}.service"
UNIT_DST="/etc/systemd/system/cryptobot-${SERVICE}@.service"

# Prefer the invoking login user when running with sudo
TARGET_USER=${SUDO_USER:-${USER}}

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


