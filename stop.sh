#!/bin/bash

# Stop Event Agent services started from this repo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "🛑 Stopping Event-Driven Agent System..."
echo ""

stop_pattern() {
    local label="$1"
    local pattern="$2"

    if pgrep -f "$pattern" > /dev/null 2>&1; then
        local pids
        pids=$(pgrep -f "$pattern" | tr '\n' ' ')
        pkill -f "$pattern" > /dev/null 2>&1 || true
        echo "✅ Stopped $label (PIDs: $pids)"
    else
        echo "ℹ️  $label not running"
    fi
}

stop_pattern "Rust API" "project-a-api"
stop_pattern "Agent Service" "uv run python main.py"
stop_pattern "Telegram Bot" "uv run python bot.py"

echo ""
echo "Done."
