import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Tuple


class EventRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _fetchall(
        self, query: str, params: Tuple[Any, ...] = ()
    ) -> List[Tuple[Any, ...]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def _fetchall_dicts(
        self, query: str, params: Tuple[Any, ...] = ()
    ) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_today_done_rows(self) -> List[Tuple[str, str]]:
        today = datetime.now().strftime("%Y-%m-%d")
        return self._fetchall(
            """
            SELECT activity, category
            FROM events
            WHERE date(timestamp) = date(?)
              AND lower(event_type) = 'done'
            ORDER BY timestamp
            """,
            (today,),
        )

    def get_bridge_rows(
        self, lookback_days: int
    ) -> List[Tuple[str, str, str, str, str]]:
        return self._fetchall(
            """
            SELECT timestamp, lower(event_type), upper(category), activity, raw_input
            FROM events
            WHERE datetime(timestamp) >= datetime('now', ?)
            ORDER BY datetime(timestamp), id
            """,
            (f"-{int(lookback_days)} days",),
        )

    def get_goal_rows(self) -> List[Tuple[str, str, str]]:
        return self._fetchall(
            """
            SELECT activity, context, raw_input
            FROM events
            WHERE upper(category) = 'GOAL'
            ORDER BY timestamp
            """
        )

    def get_today_events(self) -> List[Dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
        return self._fetchall_dicts(
            """
            SELECT timestamp, event_type, category, activity, context, raw_input
            FROM events
            WHERE date(timestamp) = date(?)
            ORDER BY timestamp
            """,
            (today,),
        )

    def get_all_dates(self) -> List[str]:
        rows = self._fetchall(
            """
            SELECT DISTINCT date(timestamp) as date
            FROM events
            ORDER BY date
            """
        )
        return [row[0] for row in rows]

    def get_events_for_date(self, date: str) -> List[Dict[str, Any]]:
        return self._fetchall_dicts(
            """
            SELECT timestamp, event_type, category, activity, context, raw_input
            FROM events
            WHERE date(timestamp) = date(?)
            ORDER BY timestamp
            """,
            (date,),
        )
