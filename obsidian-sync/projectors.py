import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


class KanbanProjector:
    def build_bridge_projection(
        self,
        rows: List[Tuple[str, str, str, str, str]],
        backlog_items: List[str],
    ) -> Dict[str, List[str]]:
        default = {"now": [], "paused": [], "captured": [], "next": []}
        if not rows:
            return default

        manual_norm = {self.normalize_task_text(item) for item in backlog_items if item}
        states: Dict[str, Dict[str, Any]] = {}
        active_key: Optional[str] = None

        for timestamp, event_type, category, activity, raw_input in rows:
            if not activity:
                continue

            key = self.normalize_task_text(activity)
            if not key:
                continue

            if event_type == "start":
                if active_key and active_key in states:
                    if states[active_key].get("status") == "active":
                        if states[active_key].get("category") != "GAME":
                            states[active_key]["status"] = "paused"

                states[key] = {
                    "status": "active",
                    "activity": self.display_activity(activity),
                    "category": category or "TASK",
                    "timestamp": timestamp,
                    "raw_input": raw_input or "",
                    "from_manual": key in manual_norm,
                }
                active_key = key

            elif event_type == "done":
                if key in states:
                    states[key]["status"] = "done"
                else:
                    states[key] = {
                        "status": "done",
                        "activity": self.display_activity(activity),
                        "category": category or "TASK",
                        "timestamp": timestamp,
                        "raw_input": raw_input or "",
                        "from_manual": key in manual_norm,
                    }
                if active_key == key:
                    active_key = None

        now_items: List[str] = []
        paused_items: List[str] = []
        captured_items: List[str] = []

        for state in states.values():
            if state.get("status") not in {"active", "paused"}:
                continue

            line = (
                f"{state['activity']} "
                f"[category:: {str(state.get('category', 'TASK')).title()}] "
                f"[source:: Event]"
            )

            if state.get("status") == "active":
                now_items.append(line)
            else:
                paused_items.append(line)

            if not state.get("from_manual"):
                captured_items.append(line)

        next_items: List[str] = []
        seen = set()

        def add_next(item_text: str) -> None:
            normalized = self.normalize_task_text(item_text)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            next_items.append(item_text)

        for item in paused_items:
            add_next(item)
            if len(next_items) >= 3:
                break

        if len(next_items) < 3:
            for item in backlog_items:
                add_next(f"{item} [source:: Manual]")
                if len(next_items) >= 3:
                    break

        if len(next_items) < 3:
            for item in captured_items:
                add_next(item)
                if len(next_items) >= 3:
                    break

        return {
            "now": now_items,
            "paused": paused_items,
            "captured": captured_items,
            "next": next_items[:3],
        }

    def map_goal_events(
        self, rows: Sequence[Tuple[Optional[str], Optional[str], Optional[str]]]
    ) -> Dict[str, List[str]]:
        section_map: Dict[str, List[str]] = {
            "Short term": [],
            "Medium Term": [],
            "Long Term": [],
            "Come back to": [],
        }

        for activity, context, raw_input in rows:
            text = self.goal_display_text(activity, raw_input)
            section = self.goal_section_from_context(context)
            if text and text not in section_map[section]:
                section_map[section].append(text)

        return section_map

    def normalize_task_text(self, text: str) -> str:
        normalized = text.lower().strip()
        normalized = re.sub(r"\[.*?\]", " ", normalized)
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def display_activity(self, activity: str) -> str:
        return activity.replace("_", " ").strip().lower()

    def goal_section_from_context(self, context: Optional[str]) -> str:
        if not context:
            return "Short term"
        normalized = str(context).strip().upper()
        if normalized == "MEDIUM_TERM":
            return "Medium Term"
        if normalized == "LONG_TERM":
            return "Long Term"
        if normalized == "COME_BACK_TO":
            return "Come back to"
        return "Short term"

    def goal_display_text(
        self, activity: Optional[str], raw_input: Optional[str]
    ) -> str:
        if raw_input:
            cleaned = re.sub(
                r"\b(add|set|create|new)\b", "", raw_input, flags=re.IGNORECASE
            )
            cleaned = re.sub(r"\b(goal|goals)\b", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(
                r"\b(short|medium|long)\s*-?\s*term\b", "", cleaned, flags=re.IGNORECASE
            )
            cleaned = re.sub(r"\bcome\s+back\s+to\b", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
            if cleaned:
                return cleaned

        if activity:
            return activity.replace("_", " ").title()

        return ""
