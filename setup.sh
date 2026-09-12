#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "======================================================="
echo "  CitySense - Self-Contained Environment Setup"
echo "======================================================="

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found in PATH. Please install Python 3.10+."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "[*] Creating local virtual environment in ./venv..."
    python3 -m venv venv
else
    echo "[*] Virtual environment already exists in ./venv"
fi

echo "[*] Upgrading pip..."
venv/bin/python -m pip install --upgrade pip

echo "[*] Installing project dependencies from requirements.txt..."
venv/bin/pip install -r requirements.txt

echo "[*] Initializing baseline AI models..."
venv/bin/python -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt')"

echo "[*] Initializing demo datasets and evidence fixtures..."
venv/bin/python scripts/seed_demo_dataset.py

echo "======================================================="
echo "  Setup Complete! Run using: ./run.sh"
echo "======================================================="
