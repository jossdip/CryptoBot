#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy/install_service.sh [service=paper]
# Services: paper (default) or live

SERVICE=${1:-paper}
UNIT_SRC="deploy/cryptobot-${SERVICE}.service"
UNIT_DST="/etc/systemd/system/cryptobot-${SERVICE}@.service"

if [[ ! -f "${UNIT_SRC}" ]]; then
  echo "Service file ${UNIT_SRC} not found." >&2
  exit 1
fi

sudo cp "${UNIT_SRC}" "${UNIT_DST}"
sudo systemctl daemon-reload
sudo systemctl enable "cryptobot-${SERVICE}@${USER}"
sudo systemctl restart "cryptobot-${SERVICE}@${USER}"
sudo systemctl status "cryptobot-${SERVICE}@${USER}" --no-pager || true


