#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -f "venv/bin/python" ]; then
    echo "[!] Virtual environment not found. Running setup.sh first..."
    ./setup.sh
fi

echo "======================================================="
echo "  Launching CitySense Edge AI Dashboard"
echo "======================================================="
venv/bin/python scripts/run_demo.py "$@"
