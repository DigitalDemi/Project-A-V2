#!/bin/bash

# Obsidian Setup Script for Event-Driven Agent
# This sets up the Obsidian vault structure and integration

set -e

echo "📓 Setting up Obsidian for Event Agent..."

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if Obsidian is installed
if ! command -v obsidian &> /dev/null; then
    echo "${YELLOW}⚠️  Obsidian not found. Installing...${NC}"
    
    # Check if yay is available
    if command -v yay &> /dev/null; then
        echo "Installing Obsidian via yay..."
        yay -S obsidian --noconfirm
    else
        echo "${YELLOW}yay not found. Please install Obsidian manually:${NC}"
        echo "Option 1: Install yay first:"
        echo "  cd /tmp && git clone https://aur.archlinux.org/yay.git"
        echo "  cd yay && makepkg -si"
        echo "  yay -S obsidian"
        echo ""
        echo "Option 2: Download AppImage:"
        echo "  mkdir -p ~/Applications"
        echo "  cd ~/Applications"
        echo "  wget https://github.com/obsidianmd/obsidian-releases/releases/download/v1.5.3/Obsidian-1.5.3.AppImage"
        echo "  chmod +x Obsidian-1.5.3.AppImage"
        echo "  ./Obsidian-1.5.3.AppImage"
        exit 1
    fi
fi

echo "${GREEN}✅ Obsidian is installed${NC}"

# Create vault directory
VAULT_PATH="$HOME/vaults/personal"
echo "Creating vault at: $VAULT_PATH"

mkdir -p "$VAULT_PATH"/{Daily,Projects,Activity,Attachments}
mkdir -p "$VAULT_PATH/.obsidian"

# Create initial daily note template
cat > "$VAULT_PATH/Templates/Daily Note.md" << 'EOF'
# {{date:YYYY-MM-DD dddd}}

## Activity Log

*Activities will be synced here automatically*

## Summary

## Notes

EOF

mkdir -p "$VAULT_PATH/Templates"

# Create README
cat > "$VAULT_PATH/README.md" << 'EOF'
# Personal Event Agent Vault

This vault is synced with your Event Agent system.

## Structure

- **Daily/** - Daily activity logs (auto-generated)
- **Projects/** - Project-specific notes
- **Activity/** - Activity summaries and patterns
- **Attachments/** - Screenshots, images, files

## How It Works

1. You log activities via Telegram: "Started pandas theory"
2. Agent parses and confirms the event
3. Event appended to master.log
4. This vault is updated with daily summaries
5. Backlinks created automatically (e.g., [[THEORY]], [[pandas]])

## Manual Sync

If you need to sync manually:
```bash
cd /path/to/basic-agent
python obsidian-sync/sync.py
```

Or sync all history:
```bash
python obsidian-sync/sync.py --all
```
EOF

echo "${GREEN}✅ Vault structure created${NC}"

# Create a sample daily note for today
TODAY=$(date +%Y-%m-%d)
cat > "$VAULT_PATH/Daily/$TODAY.md" << EOF
# $TODAY $(date +%A)

## Activity Log

*No activities logged yet today.*

Use your Telegram bot to start logging!

## Getting Started

1. Open Telegram
2. Find your Event Agent bot
3. Type: "Started working on [your activity]"
4. Confirm when the bot asks
5. Check back here to see it synced!

## Tips

- Activities appear here automatically
- Use [[Activity Name]] to create links
- Check [[Projects]] for project summaries
- Review weekly patterns in [[Activity]] folder
EOF

echo "${GREEN}✅ Created sample daily note for today ($TODAY)${NC}"

# Update .env if needed
if [ -f "/home/demi/.projects/basic-agent/.env" ]; then
    if ! grep -q "OBSIDIAN_VAULT_PATH" /home/demi/.projects/basic-agent/.env; then
        echo "OBSIDIAN_VAULT_PATH=$VAULT_PATH" >> /home/demi/.projects/basic-agent/.env
        echo "${GREEN}✅ Updated .env with vault path${NC}"
    fi
fi

echo ""
echo "${GREEN}🎉 Obsidian setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Launch Obsidian: obsidian"
echo "2. Click 'Open folder as vault'"
echo "3. Select: $VAULT_PATH"
echo "4. Start logging activities via Telegram"
echo "5. Watch them appear in Daily/ folder!"
echo ""
echo "To sync now: python obsidian-sync/sync.py"
