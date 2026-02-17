# 📓 Obsidian Integration Setup

Your Obsidian vault has been created and is ready to sync with your Event Agent!

## ✅ What's Been Created

```
~/vaults/personal/
├── .obsidian/              # Obsidian configuration
│   ├── app.json           # App settings
│   ├── appearance.json    # Theme settings
│   └── community-plugins.json
├── Daily/                 # Daily activity logs (auto-synced)
│   └── 2026-02-17.md     # Today's note (created)
├── Projects/              # Project-specific notes
├── Activity/              # Activity summaries
├── Attachments/           # Images, files
└── README.md             # Vault documentation
```

## 🔧 Install Obsidian

Since you need sudo access, run these commands in your terminal:

### Option 1: Using yay (Recommended)

```bash
# Install yay first
cd /tmp
git clone https://aur.archlinux.org/yay.git
cd yay
makepkg -si

# Install Obsidian
yay -S obsidian
```

### Option 2: Using AppImage

```bash
# Download Obsidian AppImage
mkdir -p ~/Applications
cd ~/Applications
wget https://github.com/obsidianmd/obsidian-releases/releases/download/v1.5.3/Obsidian-1.5.3.AppImage
chmod +x Obsidian-1.5.3.AppImage

# Run it
./Obsidian-1.5.3.AppImage
```

### Option 3: Using Flatpak

```bash
sudo pacman -S flatpak
flatpak install flathub md.obsidian.Obsidian
flatpak run md.obsidian.Obsidian
```

## 🚀 Open Your Vault

1. **Launch Obsidian**:
   ```bash
   obsidian
   # or
   ./Applications/Obsidian-1.5.3.AppImage
   ```

2. **Click "Open folder as vault"**

3. **Navigate to**: `~/vaults/personal`

4. **Click "Open"**

## 🔄 How Sync Works

### Automatic Sync (Recommended)

Add to your `start.sh` script or create a systemd service:

```bash
# In a new terminal, run:
watch -n 60 'cd /home/demi/.projects/basic-agent && python obsidian-sync/sync.py'
```

This syncs every 60 seconds.

### Manual Sync

```bash
cd /home/demi/.projects/basic-agent

# Sync today's events
python obsidian-sync/sync.py

# Sync all history
python obsidian-sync/sync.py --all
```

### Systemd Service (Auto-sync)

Create `~/.config/systemd/user/obsidian-sync.service`:

```ini
[Unit]
Description=Obsidian Sync for Event Agent
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash -c 'cd /home/demi/.projects/basic-agent && while true; do python obsidian-sync/sync.py; sleep 300; done'
Restart=always

[Install]
WantedBy=default.target
```

Enable it:
```bash
systemctl --user daemon-reload
systemctl --user enable obsidian-sync.service
systemctl --user start obsidian-sync.service
```

## 📱 Example Workflow

### 1. Log Activity via Telegram

```
You: "Started working on pandas theory chapter 3"
Bot: "🤔 I understood: START THEORY PANDAS. Is this correct?"
You: "Yes"
Bot: "✅ Logged: START THEORY PANDAS"
```

### 2. Check Obsidian

Open `~/vaults/personal/Daily/2026-02-17.md`:

```markdown
# 2026-02-17 Tuesday

## Activity Log

- **14:30** [[THEORY]] **[[PANDAS]]** (chapter 3)
  > Started working on pandas theory chapter 3

## Summary

**Total activities:** 1
**Breakdown:**
- THEORY: 1
```

### 3. Navigate with Backlinks

- Click `[[THEORY]]` → See all theory sessions
- Click `[[PANDAS]]` → See all pandas work
- Check [[Projects]] folder for project summaries

## 🎨 Recommended Plugins

Once Obsidian is installed, enable these community plugins:

1. **Dataview** - Query your activity data
2. **Calendar** - Navigate daily notes
3. **Periodic Notes** - Enhanced daily/weekly notes
4. **Templater** - Advanced templates

Install via: Settings → Community Plugins → Browse

## 📊 Example Queries

Add to your daily notes or a dashboard:

### Theory vs Practice This Week

```dataview
TABLE WITHOUT ID
  category AS "Category",
  count AS "Sessions",
  duration AS "Time"
FROM "Daily"
WHERE file.day >= date(today) - dur(7 days)
GROUP BY category
```

### Recent Activities

```dataview
TABLE activity, context
FROM "Daily"
SORT file.name DESC
LIMIT 10
```

## 🔗 Vault Structure

- **Daily/** - Auto-generated from your events
- **Projects/** - Manual project notes
- **Activity/** - Aggregated activity summaries
- **Attachments/** - Screenshots, diagrams

## 🛠️ Configuration

The vault is pre-configured with:

- Daily notes enabled
- Backlinks enabled
- Graph view enabled
- Auto-sync ready

## ✅ Verification Checklist

- [ ] Obsidian installed
- [ ] Vault opened at `~/vaults/personal`
- [ ] Telegram bot configured
- [ ] Test event logged
- [ ] Obsidian showing the event
- [ ] Backlinks working (click [[THEORY]])

## 🆘 Troubleshooting

### Sync not working?

1. Check vault path in `.env`:
   ```bash
   cat /home/demi/.projects/basic-agent/.env | grep OBSIDIAN
   ```

2. Run sync manually with debug:
   ```bash
   cd /home/demi/.projects/basic-agent
   python -c "from obsidian-sync.sync import ObsidianSync; s = ObsidianSync(); print(s.sync_today())"
   ```

### Events not appearing?

1. Check master.log has events:
   ```bash
   cat /home/demi/.projects/Project-A/log/master.log
   ```

2. Check SQLite has context:
   ```bash
   sqlite3 agent-service/data/context.db "SELECT * FROM events;"
   ```

### Obsidian won't open vault?

1. Ensure vault path exists:
   ```bash
   ls -la ~/vaults/personal/
   ```

2. Check permissions:
   ```bash
   ls -la ~/vaults/
   ```

## 🎉 Next Steps

1. ✅ Install Obsidian (using one of the methods above)
2. ✅ Open vault at `~/vaults/personal`
3. ✅ Start your agent: `./start.sh`
4. ✅ Log an activity via Telegram
5. ✅ Watch it appear in Obsidian!

## 📚 Resources

- [Obsidian Help](https://help.obsidian.md/)
- [Dataview Plugin Docs](https://blacksmithgu.github.io/obsidian-dataview/)
- [Event Agent README](./README.md)

---

**Status**: Vault ready, awaiting Obsidian installation
**Vault Path**: `~/vaults/personal`
**Sync Script**: `/home/demi/.projects/basic-agent/obsidian-sync/sync.py`
