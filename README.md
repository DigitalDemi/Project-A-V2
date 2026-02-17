# Event-Driven Agent System

A privacy-focused, evolving agent for time tracking, task management, and learning logs that grows with your needs.

## Architecture

This system follows an **event-driven architecture** where:
- **master.log** is the single source of truth (append-only, never edited)
- All state is **derived from events** through projections
- **LLM is advisory** - suggests but never writes directly to the log
- Human intent is the **final authority**

### Core Components

```
Telegram Bot → Agent Service → Rust API → master.log (source of truth)
                    ↓               ↓
              SQLite context   Projections (sessions, ratios)
                    ↓               ↓
              LLM training    Obsidian sync
```

## Quick Start

### Prerequisites

- Arch Linux (or similar)
- Python 3.11+
- Rust
- SQLite
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Installation

```bash
# Clone and enter directory
cd /path/to/basic-agent

# Run setup script
chmod +x setup.sh
./setup.sh

# Download LLM model (optional, for advanced parsing)
chmod +x download-model.sh
./download-model.sh

# Configure environment
cp .env.example .env
# Edit .env and add your TELEGRAM_BOT_TOKEN

# Start all services
chmod +x start.sh
./start.sh
```

## Usage

### Via Telegram

Just tell the bot what you're doing in natural language:

```
You: "Starting pandas theory chapter 3"
Bot: "🤔 I understood: START THEORY pandas. Is this correct?"
You: "Yes"
Bot: "✅ Logged: START THEORY pandas"

You: "Done with the database refactor"
Bot: "🤔 I understood: DONE TASK database. Is this correct?"
You: "No, it was practice"
Bot: "🔄 Corrected: DONE PRACTICE database. Is this correct now?"
You: "Yes"
```

### Queries

Ask about your activities:

```
You: "What did I work on yesterday?"
Bot: "Recent sessions:
- THEORY pandas
- PRACTICE rust
- GAME Valorant"

You: "Theory to practice ratio this week?"
Bot: "Theory to Practice Ratio (week):
Total sessions: 15
Breakdown: {'THEORY': 6, 'PRACTICE': 9}
Ratio: 0.67"
```

### Commands

- `/start` - Welcome message
- `/help` - Show help
- `/ratio` - Show theory to practice ratio
- `/today` - Today's summary

## System Design

### Invariants (Never Broken)

1. **Event log is append-only** - Events are never edited or deleted
2. **Events are never corrected** - Imperfections remain in historical record
3. **Inference is pure and replayable** - Same events always produce same projections
4. **UI does not own state** - Only emits events and renders projections
5. **Meaning is derived, not stored** - Projections can be rebuilt anytime

### Event Format

```
START THEORY pandas
START PRACTICE rust
DONE TASK refactor
NOTE pytorch data loaders are tricky
```

### Session Derivation

Sessions are inferred, not logged:
- Start of new activity = end of previous session
- No explicit "stop" needed
- Activities can recur many times

## Evolution Path

### Phase 1: Foundation (Now)
- Rule-based parsing
- Telegram interface
- Basic projections (sessions, ratios)
- SQLite context storage

### Phase 2: LLM Integration (Month 2)
- Local Qwen 2.5 3B model
- Natural language parsing
- Complex query handling
- Training data collection

### Phase 3: Personalization (Month 3-4)
- Fine-tune on your patterns
- Predictive suggestions
- Pattern detection
- Smart reminders

### Phase 4: Advanced Features (Month 5+)
- Obsidian bidirectional sync
- Habit tracking
- Goal setting
- Weekly/monthly reviews

## File Structure

```
basic-agent/
├── agent-service/          # Python LLM service
│   ├── src/
│   │   ├── main.py        # FastAPI app
│   │   ├── parser.py      # Event parser
│   │   └── query_engine.py # Analytics
│   ├── models/            # Downloaded LLMs
│   ├── data/              # SQLite database
│   └── logs/              # LLM decisions
│
├── telegram-bot/          # Telegram interface
│   └── src/
│       └── bot.py         # Bot logic
│
├── Project-A-extension/   # Rust HTTP API
│   └── src/
│       ├── main.rs        # Axum server
│       ├── models.rs      # Data structures
│       └── projections.rs # Session/ratio logic
│
├── obsidian-sync/         # Obsidian integration
│   └── sync.py           # Daily note sync
│
├── setup.sh              # Installation script
├── start.sh              # Start all services
├── download-model.sh     # Download LLM
└── .env                  # Configuration
```

## API Endpoints

### Agent Service (Python) - Port 8000

- `POST /parse` - Parse natural language into event
- `POST /confirm` - Confirm/correct parsed event
- `POST /query` - Complex queries

### Rust API - Port 8080

- `POST /events` - Append event to master.log
- `GET /events` - List all events
- `POST /query` - Query projections
- `GET /projections/sessions` - Session timeline
- `GET /projections/ratios` - Category ratios

## Training Your Own Model

The system collects training data automatically:

```sql
-- LLM decisions stored in SQLite
SELECT * FROM llm_decisions;

-- Schema:
-- user_input: What user typed
-- llm_suggestion: What LLM suggested
-- user_response: "Yes" or correction
-- confidence: How sure LLM was
```

After 2-4 weeks of usage:

1. Export training data
2. Fine-tune LoRA adapter on Qwen 2.5 3B
3. Deploy personalized model
4. Continue collecting data for iteration

## Privacy

- **All data local** - No cloud dependencies
- **Self-hosted** - Runs on your hardware
- **No data sharing** - Events stay in your files
- **Open source** - Full transparency

## Development

### Running Tests

```bash
# Python tests
cd agent-service
source venv/bin/activate
pytest

# Rust tests
cd Project-A-extension
cargo test
```

### Adding New Features

1. **New Event Types**: Update `parser.py` and Rust models
2. **New Projections**: Add to `projections.rs`
3. **New Queries**: Extend `query_engine.py`
4. **New Tools**: Follow event-driven pattern

## Troubleshooting

### Services won't start

```bash
# Check ports
sudo lsof -i :8000  # Agent service
sudo lsof -i :8080  # Rust API

# Check logs
sudo journalctl -u agent-service
sudo journalctl -u rust-api
```

### LLM not responding

- Check if model downloaded: `ls agent-service/models/`
- Check memory: Models need 4-8GB RAM
- Fall back to rule-based: Set `use_llm: false`

### Telegram bot not responding

- Verify token in `.env`
- Check bot is running: `sudo systemctl status telegram-bot`
- Check webhook not set: Must use polling mode

## License

MIT - Free to use, modify, and distribute.

## Contributing

This is a personal system that grows with use. Adapt it to your needs, and share improvements if you'd like!

## Acknowledgments

Built on the principles of:
- Event sourcing
- CQRS (Command Query Responsibility Segregation)
- Append-only logs
- Privacy-by-design

Inspired by time tracking systems, learning logs, and the desire for a tool that understands context rather than forcing structure.
