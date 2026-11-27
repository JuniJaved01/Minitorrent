#!/bin/bash
# Double-click this file on macOS to launch MiniTorrent.
# (macOS runs .command files in Terminal automatically.)

cd "$(dirname "$0")"

echo "=============================================="
echo "  MiniTorrent P2P File Sharing System"
echo "=============================================="
echo ""
echo "Starting application..."
echo "Default URL: http://localhost:9090"
echo "(If that port is blocked, the app will"
echo " automatically find the next free port.)"
echo ""

./minitorrent

echo ""
echo "Application stopped."
read -n 1 -s -r -p "Press any key to close..."
