#!/bin/bash
# ========================================================
# LockTrace Community Node Launcher for Linux & macOS
# ========================================================
set -e

echo "=== 🛡️ LockTrace Node Setup ==="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required. Please install python3."
    exit 1
fi

# Create virtual environment if not present
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

read -p "Enter your Node Name (e.g., Istanbul-Node-01): " NODE_NAME
read -p "Enter your Geographic Location (e.g., Istanbul, TR): " NODE_LOC

NODE_NAME=${NODE_NAME:-"Community-Peer"}
NODE_LOC=${NODE_LOC:-"Global"}

echo "Starting LockTrace Node daemon..."
python3 node_runner.py --name "$NODE_NAME" --location "$NODE_LOC"

