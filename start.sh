#!/bin/bash

# Start all services
# For development use

echo "🚀 Starting Event-Driven Agent System..."
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup EXIT

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Copy .env.example to .env and add your Telegram bot token"
    exit 1
fi

# Start Rust API
echo "Starting Rust API (port 8080)..."
cd Project-A-extension
cargo run --release &
RUST_PID=$!
cd ..

sleep 3

# Start Agent Service
echo "Starting Agent Service (port 8000)..."
cd agent-service
source venv/bin/activate
python src/main.py &
AGENT_PID=$!
cd ..

sleep 2

# Start Telegram Bot
echo "Starting Telegram Bot..."
cd telegram-bot
source venv/bin/activate
python src/bot.py &
BOT_PID=$!
cd ..

echo ""
echo "✅ All services started!"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for all background jobs
wait
