#!/bin/bash

# Restart Event Agent services
# Usage:
#   ./restart.sh           # daemon mode
#   ./restart.sh --interactive

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

MODE="--daemon"
if [ "$1" = "--interactive" ]; then
    MODE=""
fi

./stop.sh
echo ""

if [ -n "$MODE" ]; then
    ./start.sh --daemon
else
    ./start.sh
fi
