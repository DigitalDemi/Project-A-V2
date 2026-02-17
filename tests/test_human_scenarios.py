import sqlite3
import tempfile
from pathlib import Path

import sys

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "agent-service" / "src"))
sys.path.insert(0, str(BASE / "obsidian-sync"))

from parser import EventParser
from main import _motivation_for_event
from sync import ObsidianSync


def _init_events_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            category TEXT,
            activity TEXT,
            context TEXT,
            raw_input TEXT,
            user_confirmed BOOLEAN,
            log_position INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()
    conn.close()


def test_human_goal_phrase_parses_to_goal_event():
    parser = EventParser()

    result = parser.parse("add goal short term learn music theory")

    assert result["category"] == "GOAL"
    assert result["context"] == "SHORT_TERM"
    assert result["formatted_event"].startswith("START GOAL ")


def test_human_done_flow_returns_motivation():
    parsed_event = {
        "action": "done",
        "category": "TASK",
        "activity": "Laundry",
    }

    msg = _motivation_for_event(parsed_event)

    assert msg is not None
    assert "Laundry" in msg or "laundry" in msg


def test_kanban_goal_board_updates_from_goal_events():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        vault = tmp_path / "vault"
        db = tmp_path / "context.db"

        _init_events_db(db)

        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO events (timestamp, event_type, category, activity, context, raw_input, user_confirmed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                "2026-02-17T13:00:00",
                "start",
                "GOAL",
                "LEARN_MUSIC_THEORY",
                "SHORT_TERM",
                "add goal short term learn music theory",
                True,
            ),
        )
        conn.commit()
        conn.close()

        sync = ObsidianSync(vault_path=str(vault), db_path=str(db))
        updated = sync.sync_kanban_projections()

        assert any("Goals Board.md" in p for p in updated)

        goals_board = vault / "Kanban" / "Goals Board.md"
        content = goals_board.read_text()
        assert "## Short term" in content
        assert "- [ ] learn music theory" in content.lower()
        assert "## Medium Term" in content
        assert "learn music theory## Medium Term" not in content
