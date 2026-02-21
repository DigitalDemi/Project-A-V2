"""
Query Engine - Complex analytics and insights from event log
Respects invariants: only reads, never writes
"""

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


class QueryEngine:
    """
    Handles complex queries by analyzing event log + context
    Never modifies master.log, only derives projections
    """

    def __init__(self, db_path: Optional[str] = None, log_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = db_path or os.path.join(base_dir, "data", "context.db")
        self.log_path = log_path or os.path.join(
            base_dir, "..", "Project-A-extension", "log", "master.log"
        )
        self.init_database()

    def init_database(self):
        """Initialize SQLite database for context storage"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Events table - rich metadata (not the source of truth)
            cursor.execute("""
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
            """)

            # LLM decisions for training
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS llm_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    user_input TEXT,
                    llm_suggestion TEXT,
                    user_response TEXT,
                    confidence REAL,
                    model TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Derived sessions (projection)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity TEXT,
                    category TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    duration_minutes INTEGER,
                    event_ids TEXT,  -- JSON array of event IDs
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def read_master_log(self) -> List[str]:
        """Read master.log - source of truth"""
        try:
            with open(self.log_path, "r") as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def derive_sessions(self) -> List[Dict[str, Any]]:
        """
        Derive sessions with SQLite as canonical source.
        Falls back to master.log replay when DB has no start events.
        """
        sessions = self._derive_sessions_from_db()
        if sessions:
            return sessions
        return self._derive_sessions_from_log()

    def _derive_sessions_from_db(self) -> List[Dict[str, Any]]:
        try:
            start_rows = self._fetchall(
                """
                SELECT timestamp, upper(category), activity
                FROM events
                WHERE lower(event_type) = 'start'
                ORDER BY datetime(timestamp), id
                """
            )
        except Exception:
            return []

        if not start_rows:
            return []

        sessions: List[Dict[str, Any]] = []
        for i, (timestamp, category, activity) in enumerate(start_rows):
            session: Dict[str, Any] = {
                "category": category or "TASK",
                "activity": activity or "unknown",
                "start_timestamp": timestamp,
                "start_event_index": i,
            }

            start_dt = self._safe_parse_iso(timestamp)
            next_dt = (
                self._safe_parse_iso(start_rows[i + 1][0])
                if i + 1 < len(start_rows)
                else None
            )

            if start_dt and next_dt:
                duration = int((next_dt - start_dt).total_seconds() / 60)
                session["duration_minutes"] = max(duration, 0)
                session["end_timestamp"] = start_rows[i + 1][0]
                session["end_event_index"] = i
                session["is_active"] = False
            elif start_dt:
                duration = int((datetime.now() - start_dt).total_seconds() / 60)
                session["duration_minutes"] = max(duration, 0)
                session["duration_display"] = self._format_duration(
                    session["duration_minutes"]
                )
                session["end_event_index"] = len(start_rows) - 1
                session["is_active"] = True
            else:
                session["duration_minutes"] = None
                session["end_event_index"] = len(start_rows) - 1
                session["is_active"] = i == len(start_rows) - 1

            sessions.append(session)

        return sessions

    def _derive_sessions_from_log(self) -> List[Dict[str, Any]]:
        events = self.read_master_log()
        sessions: List[Dict[str, Any]] = []

        for idx, event_line in enumerate(events):
            parsed = self._parse_start_line(event_line)
            if not parsed:
                continue

            if sessions:
                sessions[-1]["is_active"] = False
                sessions[-1]["end_event_index"] = idx - 1
            category, activity = parsed
            sessions.append(
                {
                    "category": category,
                    "activity": activity,
                    "duration_minutes": None,
                    "is_active": True,
                    "start_event_index": idx,
                    "raw_line": event_line,
                }
            )

        if sessions:
            sessions[-1]["end_event_index"] = len(events) - 1

        return sessions

    def _parse_start_line(self, line: str) -> Optional[tuple[str, str]]:
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            return None
        if parts[0].upper() != "START":
            return None
        return parts[1].upper(), parts[2]

    def _safe_parse_iso(self, timestamp: Optional[str]) -> Optional[datetime]:
        if not timestamp:
            return None
        try:
            return datetime.fromisoformat(timestamp)
        except Exception:
            return None

    def _format_duration(self, minutes: int) -> str:
        """Format duration in human-readable form"""
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        mins = minutes % 60
        if hours < 24:
            return f"{hours}h {mins}m"
        days = hours // 24
        hours = hours % 24
        return f"{days}d {hours}h {mins}m"

    def calculate_ratios(self, timeframe: str = "week") -> Dict[str, Any]:
        """
        Calculate theory to practice ratios
        Timeframe: 'day', 'week', 'month'
        """
        sessions = self.derive_sessions()

        counts = {"THEORY": 0, "PRACTICE": 0, "TASK": 0, "GAME": 0}

        for session in sessions:
            cat = session.get("category", "UNKNOWN")
            if cat in counts:
                counts[cat] += 1

        total = sum(counts.values())
        if total == 0:
            return {"error": "No data available"}

        return {
            "timeframe": timeframe,
            "total_sessions": total,
            "breakdown": counts,
            "ratios": {
                cat: round(count / total * 100, 1) for cat, count in counts.items()
            },
            "theory_to_practice": round(
                counts["THEORY"] / max(counts["PRACTICE"], 1), 2
            ),
        }

    def calculate_time_spent(
        self,
        timeframe: str = "day",
        category: Optional[str] = None,
        activity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Approximate time spent from derived sessions.
        Uses session start date for timeframe filtering.
        """
        sessions = self.derive_sessions()
        now = datetime.now()

        def in_timeframe(session: Dict[str, Any]) -> bool:
            ts = session.get("start_timestamp")
            if not ts:
                return timeframe in {"all", "week", "month"}

            parsed = self._safe_parse_iso(ts)
            if not parsed:
                return False

            if timeframe == "day":
                return parsed.date() == now.date()
            if timeframe == "week":
                return (now - parsed).days < 7
            if timeframe == "month":
                return (now - parsed).days < 30
            return True

        filtered = [s for s in sessions if in_timeframe(s)]

        if category:
            cat = category.upper()
            filtered = [s for s in filtered if (s.get("category") or "").upper() == cat]

        if activity:
            act = activity.strip().lower()
            filtered = [
                s for s in filtered if act in str(s.get("activity", "")).lower()
            ]

        total_minutes = sum(
            int(s.get("duration_minutes") or 0)
            for s in filtered
            if isinstance(s.get("duration_minutes"), int)
            or (
                isinstance(s.get("duration_minutes"), str)
                and str(s.get("duration_minutes")).isdigit()
            )
        )

        activity_rollup: Dict[str, Dict[str, int]] = {}
        for session in filtered:
            key = str(session.get("activity") or "unknown")
            if key not in activity_rollup:
                activity_rollup[key] = {"minutes": 0, "sessions": 0}

            raw_minutes = session.get("duration_minutes")
            minutes = (
                int(raw_minutes)
                if isinstance(raw_minutes, int)
                or (isinstance(raw_minutes, str) and str(raw_minutes).isdigit())
                else 0
            )

            activity_rollup[key]["minutes"] += max(minutes, 0)
            activity_rollup[key]["sessions"] += 1

        by_activity = [
            {
                "activity": activity_name,
                "minutes": stats["minutes"],
                "display": self._format_duration(stats["minutes"]),
                "sessions": stats["sessions"],
            }
            for activity_name, stats in activity_rollup.items()
        ]
        by_activity.sort(key=lambda x: (x["minutes"], x["sessions"]), reverse=True)

        return {
            "timeframe": timeframe,
            "category": category.upper() if category else None,
            "activity": activity,
            "total_minutes": total_minutes,
            "total_display": self._format_duration(total_minutes),
            "session_count": len(filtered),
            "by_activity": by_activity,
        }

    def answer_query(self, query: str, timeframe: str = "week") -> Dict[str, Any]:
        """
        Answer natural language queries
        Examples:
        - "What did I work on yesterday?"
        - "Theory to practice ratio this week?"
        - "How much time on pandas?"
        """
        query_lower = query.lower()

        # Pattern matching for query types
        if "ratio" in query_lower:
            return {"type": "ratio", "answer": self.calculate_ratios(timeframe)}

        if (
            "how much time" in query_lower
            or "time spent" in query_lower
            or "spent on" in query_lower
        ):
            inferred_timeframe = timeframe
            if "today" in query_lower:
                inferred_timeframe = "day"
            elif "week" in query_lower:
                inferred_timeframe = "week"
            elif "month" in query_lower:
                inferred_timeframe = "month"

            category = None
            for known in ("theory", "practice", "task", "game"):
                if known in query_lower:
                    category = known
                    break

            activity = None
            if " on " in query_lower and not category:
                activity = query_lower.split(" on ", 1)[1].strip().rstrip("?")

            return {
                "type": "time_spent",
                "answer": self.calculate_time_spent(
                    inferred_timeframe, category=category, activity=activity
                ),
            }

        elif (
            "yesterday" in query_lower
            or "last" in query_lower
            or "timeline" in query_lower
            or "sessions" in query_lower
        ):
            sessions = self.derive_sessions()
            return {
                "type": "timeline",
                "answer": {
                    "recent_sessions": sessions[-5:] if sessions else [],
                    "count": len(sessions),
                },
            }

        elif (
            "what did i" in query_lower
            or "work on" in query_lower
            or "today" in query_lower
            or "summary" in query_lower
        ):
            sessions = self.derive_sessions()
            activities = list(set(s["activity"] for s in sessions))
            return {
                "type": "summary",
                "answer": {
                    "activities": activities,
                    "total_activities": len(activities),
                },
            }

        else:
            return {
                "type": "unknown",
                "answer": "I can tell you about your ratios, recent work, or activity summary. What would you like to know?",
            }

    def store_context(self, event_data: Dict[str, Any]):
        """Store rich context in SQLite (not master.log)"""
        self._execute(
            """
            INSERT INTO events 
            (timestamp, event_type, category, activity, context, raw_input, user_confirmed, log_position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                event_data.get("timestamp"),
                event_data.get("action"),
                event_data.get("category"),
                event_data.get("activity"),
                event_data.get("context"),
                event_data.get("raw_input"),
                event_data.get("user_confirmed", False),
                event_data.get("log_position"),
            ),
        )

    def store_llm_decision(self, decision: Dict[str, Any]):
        """Store LLM decision for future training"""
        self._execute(
            """
            INSERT INTO llm_decisions 
            (timestamp, user_input, llm_suggestion, user_response, confidence, model)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                decision.get("timestamp"),
                decision.get("user_input"),
                decision.get("llm_suggestion"),
                decision.get("user_response"),
                decision.get("confidence"),
                decision.get("model", "qwen-2.5-3b"),
            ),
        )

    def _execute(self, query: str, params: tuple = ()) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

    def _fetchall(self, query: str, params: tuple = ()) -> List[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()


if __name__ == "__main__":
    engine = QueryEngine()

    # Test queries
    print("Testing query engine...")
    print("Sessions:", engine.derive_sessions())
    print("Ratios:", engine.calculate_ratios())
    print("Query 'what did I work on':", engine.answer_query("what did I work on"))
