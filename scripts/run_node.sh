#!/bin/bash
# =====================================================================
# LockTrace Decentralized Node & Verified Web Launcher (Linux & macOS)
# =====================================================================
set -e

echo "=== LockTrace Decentralized Node & Web Setup (v2.8.9) ==="

if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required. Please install python3."
    exit 1
fi

read -r -p "Dugum Adi (orn: Istanbul-Node-01): " NODE_NAME
read -r -p "Konum (orn: Istanbul, TR): " NODE_LOC
NODE_NAME=${NODE_NAME:-"Community-Peer"}
NODE_LOC=${NODE_LOC:-"Global"}

echo ""
echo "Frontend Calisma Modunu Secin:"
echo "  [1] Yerel Mod (Sadece bu bilgisayarda ac: http://127.0.0.1:5050 + Tarayiciyi Ac)"
echo "  [2] Sunucu Modu (Agda / Internette sunucu olarak ac: http://0.0.0.0:5050)"
echo "  [3] Sadece P2P Madenci/Dogrulayici (Web arayuzu kapali)"
read -r -p "Seciminiz (Varsayilan: 2): " MODE

if [ "$MODE" = "1" ]; then
    python3 node_runner.py --name "$NODE_NAME" --location "$NODE_LOC" --local --open
elif [ "$MODE" = "3" ]; then
    python3 node_runner.py --name "$NODE_NAME" --location "$NODE_LOC" --no-web
else
    python3 node_runner.py --name "$NODE_NAME" --location "$NODE_LOC" --server --port 5050
fi
