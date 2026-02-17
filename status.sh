#!/bin/bash

# Status checker for Event Agent services

echo "📊 Event Agent System Status"
echo "============================"
echo ""

# Check Rust API
echo -n "🦀 Rust API (Port 8080): "
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "✅ Running"
    curl -s http://localhost:8080/ | sed 's/^/   /'
else
    echo "❌ Not running"
fi
echo ""

# Check Agent Service
echo -n "🐍 Agent Service (Port 8000): "
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Running"
    curl -s http://localhost:8000/health | grep -o '"status":"[^"]*"' | sed 's/^/   /'
else
    echo "❌ Not running"
fi
echo ""

# Check Telegram Bot
echo -n "💬 Telegram Bot: "
if pgrep -f "uv run python bot.py" > /dev/null; then
    PID=$(pgrep -f "uv run python bot.py")
    echo "✅ Running (PID: $PID)"
else
    echo "❌ Not running"
fi
echo ""

# Check master.log
echo "📁 master.log:"
if [ -f ../Project-A/log/master.log ]; then
    LINE_COUNT=$(wc -l < ../Project-A/log/master.log)
    echo "   ✅ Exists ($LINE_COUNT events)"
    echo "   Last 3 events:"
    tail -3 ../Project-A/log/master.log | sed 's/^/   /'
else
    echo "   ❌ Not found"
fi
echo ""

# Check Obsidian Vault
echo "📓 Obsidian Vault:"
if [ -d ~/vaults/personal ]; then
    echo "   ✅ Exists at ~/vaults/personal"
    echo "   Daily notes: $(ls ~/vaults/personal/Daily/ 2>/dev/null | wc -l)"
else
    echo "   ❌ Not found"
fi
echo ""

echo "============================"
echo ""
echo "📱 Try your bot on Telegram!"
echo "Type: 'Started working on pandas theory'"
