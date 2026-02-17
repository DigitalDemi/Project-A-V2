#!/bin/bash

# Setup script for Event-Driven Agent System
# Runs on Arch Linux

set -e

echo "🚀 Setting up Event-Driven Agent System..."
echo ""

# Check if running on Arch Linux
if ! grep -q "Arch Linux" /etc/os-release 2>/dev/null; then
    echo "⚠️  Warning: This script is designed for Arch Linux"
    echo "Continuing anyway..."
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "${GREEN}Step 1: Installing system dependencies...${NC}"
sudo pacman -S --needed python rustup sqlite curl base-devel

# Install uv if missing
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

export PATH="$HOME/.local/bin:$PATH"

# Ensure Python 3.12 is available for this project
echo "Ensuring Python 3.12 is available..."
uv python install 3.12

# Install Rust
if ! command -v rustc &> /dev/null; then
    echo "Installing Rust..."
    rustup default stable
fi

echo ""
echo "${GREEN}Step 2: Setting up Python virtual environments...${NC}"

# Agent Service
if [ ! -d "agent-service/.venv" ]; then
    echo "Creating agent-service virtual environment..."
    cd agent-service
    uv venv --python 3.12
    uv pip install -r requirements.txt
    cd ..
fi

# Telegram Bot
if [ ! -d "telegram-bot/.venv" ]; then
    echo "Creating telegram-bot virtual environment..."
    cd telegram-bot
    uv venv --python 3.12
    uv pip install -r requirements.txt
    cd ..
fi

echo ""
echo "${GREEN}Step 3: Setting up directories...${NC}"

# Create data directories
mkdir -p agent-service/data
mkdir -p agent-service/logs
mkdir -p agent-service/models
mkdir -p telegram-bot/logs

# Create log file if doesn't exist
if [ ! -f "../Project-A/log/master.log" ]; then
    echo "Creating master.log..."
    mkdir -p ../Project-A/log
    touch ../Project-A/log/master.log
fi

echo ""
echo "${GREEN}Step 4: Setting up environment files...${NC}"

if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "${YELLOW}⚠️  Please edit .env and add your Telegram bot token!${NC}"
fi

echo ""
echo "${GREEN}Step 5: Building Rust API...${NC}"

cd Project-A-extension
cargo build --release
cd ..

echo ""
echo "${GREEN}Step 6: Setting up systemd services (optional)...${NC}"

read -p "Create systemd services for auto-start? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Create systemd service files
    cat > /tmp/agent-service.service << EOF
[Unit]
Description=Event Agent LLM Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD/agent-service
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin
ExecStart=$HOME/.local/bin/uv run --directory $PWD/agent-service python src/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

    cat > /tmp/telegram-bot.service << EOF
[Unit]
Description=Event Agent Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD/telegram-bot
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin
ExecStart=$HOME/.local/bin/uv run --directory $PWD/telegram-bot python src/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

    cat > /tmp/rust-api.service << EOF
[Unit]
Description=Event Agent Rust API
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD/Project-A-extension
ExecStart=$PWD/Project-A-extension/target/release/project-a-api
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

    sudo cp /tmp/agent-service.service /etc/systemd/system/
    sudo cp /tmp/telegram-bot.service /etc/systemd/system/
    sudo cp /tmp/rust-api.service /etc/systemd/system/
    
    sudo systemctl daemon-reload
    
    echo "${GREEN}Services created!${NC}"
    echo "Enable with: sudo systemctl enable agent-service telegram-bot rust-api"
    echo "Start with: sudo systemctl start agent-service telegram-bot rust-api"
fi

echo ""
echo "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your Telegram bot token"
echo "2. Download LLM model: ./download-model.sh"
echo "3. Start services: ./start.sh"
echo ""
echo "Manual start:"
echo "  Terminal 1: cd Project-A-extension && cargo run"
echo "  Terminal 2: cd agent-service/src && uv run python main.py"
echo "  Terminal 3: cd telegram-bot/src && uv run python bot.py"
