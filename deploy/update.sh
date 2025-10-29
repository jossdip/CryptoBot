#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy/update.sh [service=paper]

SERVICE=${1:-paper}

cd /home/$USER/CryptoBot
git pull --ff-only || true

source .venv/bin/activate
pip install -r requirements.txt || true

sudo systemctl restart "cryptobot-${SERVICE}@${USER}"
sudo systemctl status "cryptobot-${SERVICE}@${USER}" --no-pager || true


