#!/usr/bin/env bash
# Phase 1: Install and verify Stockfish on the Linode server.
# Run this on the Linode server (not locally).
#
# Usage:
#   chmod +x linode_setup_stockfish.sh
#   ./linode_setup_stockfish.sh

set -e

echo "=== Installing Stockfish ==="
sudo apt update -q
sudo apt install -y stockfish

STOCKFISH_BIN=$(which stockfish)
echo "Stockfish installed at: $STOCKFISH_BIN"

echo ""
echo "=== Smoke-testing Stockfish binary ==="
echo "uci" | "$STOCKFISH_BIN" | grep -m1 "^id name" && echo "Binary: OK"

echo ""
echo "=== Installing python-chess (needed for the Python smoke-test) ==="
pip3 install chess --quiet

echo ""
echo "=== Smoke-testing Stockfish via python-chess ==="
python3 - << PYEOF
import chess.engine

path = "$(which stockfish)"
engine = chess.engine.SimpleEngine.popen_uci(path)
board = chess.Board()
info = engine.analyse(board, chess.engine.Limit(depth=12))
score = info["score"].white()
engine.quit()
print(f"Score from starting position: {score}")
print("python-chess + Stockfish: OK")
PYEOF

echo ""
echo "=== Done ==="
echo ""
echo "Add this line to the app's .env when you deploy:"
echo "  STOCKFISH_PATH=$(which stockfish)"
