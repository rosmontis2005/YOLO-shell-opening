#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  libgl1 \
  libglib2.0-0 \
  libsm6 \
  libxext6 \
  libxrender1 \
  v4l-utils

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo
echo "Python environment is ready."
echo "Activate it with: source .venv/bin/activate"
echo "For Arduino serial access, run this once and then log out/in:"
echo "  sudo usermod -aG dialout \$USER"
