#!/bin/bash

# Start all services
# Usage:
#   ./start.sh            # interactive mode (Ctrl+C stops all)
#   ./start.sh --daemon   # detached mode

echo "🚀 Starting Event-Driven Agent System..."
echo ""

DAEMON_MODE=0
if [ "$1" = "--daemon" ]; then
    DAEMON_MODE=1
fi

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $(jobs -p) 2>/dev/null
    exit
}

if [ "$DAEMON_MODE" -eq 0 ]; then
    trap cleanup EXIT
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Copy .env.example to .env and add your Telegram bot token"
    exit 1
fi

export PATH="$HOME/.local/bin:$PATH"

if [ "$DAEMON_MODE" -eq 1 ]; then
    echo "Starting Rust API (port 8080) in daemon mode..."
    (
        cd Project-A-extension || exit 1
        nohup cargo run --release > "/home/demi/.projects/basic-agent/.rust-api.log" 2>&1 &
    )

    echo "Starting Agent Service (port 8000) in daemon mode..."
    (
        cd agent-service/src || exit 1
        nohup uv run python main.py > "/home/demi/.projects/basic-agent/.agent-service.log" 2>&1 &
    )

    echo "Starting Telegram Bot in daemon mode..."
    (
        cd telegram-bot/src || exit 1
        nohup uv run python bot.py > "/home/demi/.projects/basic-agent/.bot-aiogram.log" 2>&1 &
    )

    echo ""
    echo "✅ All services started in daemon mode"
    echo "Logs: .rust-api.log, .agent-service.log, .bot-aiogram.log"
    echo ""
    exit 0
fi

# Interactive mode
echo "Starting Rust API (port 8080)..."
cd Project-A-extension
cargo run --release &
RUST_PID=$!
cd ..

sleep 3

echo "Starting Agent Service (port 8000)..."
cd agent-service/src
uv run python main.py &
AGENT_PID=$!
cd ..
cd ..

sleep 2

echo "Starting Telegram Bot..."
cd telegram-bot/src
uv run python bot.py &
BOT_PID=$!
cd ..
cd ..

echo ""
echo "✅ All services started!"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

wait
