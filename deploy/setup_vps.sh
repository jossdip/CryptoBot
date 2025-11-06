#!/usr/bin/env bash
set -euo pipefail

# Usage: ./deploy/setup_vps.sh <repo_url> [branch]
# Example: ./deploy/setup_vps.sh https://github.com/jossdip/CryptoBot.git main
# Or with SSH: ./deploy/setup_vps.sh git@github.com:jossdip/CryptoBot.git main

REPO_URL=${1:-}
BRANCH=${2:-main}

if [[ -z "${REPO_URL}" ]]; then
  echo "Provide repo URL: ./deploy/setup_vps.sh <repo_url> [branch]" >&2
  exit 1
fi

sudo apt update
sudo apt -y upgrade
sudo apt -y install git python3 python3-venv python3-pip

cd /home/$USER
if [[ ! -d CryptoBot ]]; then
  git clone "${REPO_URL}" CryptoBot
fi
cd CryptoBot
git fetch --all
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}" || true

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
else
  pip install -e .
fi

# Ensure console scripts (cryptobot, cb) are installed
pip install -e .

if [[ ! -f .env ]]; then
  echo "Creating .env from configs/deepseek.env.sample (edit with your keys)"
  cp configs/deepseek.env.sample .env || true
fi

echo "VPS setup done. Fill /home/$USER/CryptoBot/.env before installing the service."


