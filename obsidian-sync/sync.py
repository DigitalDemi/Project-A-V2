"""
Obsidian Sync - Updates Obsidian vault from event log
One-way sync: log → Obsidian (projection layer)
"""

import re
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv

try:
    from .repository import EventRepository
    from .projectors import KanbanProjector
    from .renderers import BoardRenderer
except ImportError:
    from repository import EventRepository
    from projectors import KanbanProjector
    from renderers import BoardRenderer


class ObsidianSync:
    """
    Syncs event data to Obsidian vault
    Creates/updates daily notes with activity logs
    """

    def __init__(self, vault_path: Optional[str] = None, db_path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent
        load_dotenv(base_dir / ".env")

        resolved_vault = vault_path or os.getenv(
            "OBSIDIAN_VAULT_PATH", "~/vaults/personal"
        )
        self.vault_path = Path(resolved_vault).expanduser()
        self.db_path = (
            str(Path(db_path))
            if db_path
            else str(base_dir / "agent-service" / "data" / "context.db")
        )
        self.project_todo_path = base_dir.parent / "Project-A" / "TODO.md"
        self.daily_notes_path = self.vault_path / "Daily"
        self.kanban_path = self.vault_path / "Kanban"

        # Ensure directories exist
        self.daily_notes_path.mkdir(parents=True, exist_ok=True)
        self.kanban_path.mkdir(parents=True, exist_ok=True)
        self.repository = EventRepository(self.db_path)
        self.projector = KanbanProjector()
        self.renderer = BoardRenderer()

    def sync_today(self) -> str:
        """Sync today's events to Obsidian"""
        today = datetime.now()
        note_path = self.daily_notes_path / f"{today.strftime('%Y-%m-%d')}.md"

        # Get today's events from SQLite
        events = self._get_today_events()

        # Generate note content
        content = self._generate_note_content(today, events)

        # Write to file
        note_path.write_text(content)

        return str(note_path)

    def sync_all(self) -> List[str]:
        """Sync all events to Obsidian (useful for initial setup)"""
        updated_notes = []

        # Get all unique dates
        dates = self._get_all_dates()

        for date in dates:
            events = self._get_events_for_date(date)
            note_path = self.daily_notes_path / f"{date}.md"

            content = self._generate_note_content(
                datetime.strptime(date, "%Y-%m-%d"), events
            )
            note_path.write_text(content)
            updated_notes.append(str(note_path))

        return updated_notes

    def sync_kanban_projections(self) -> List[str]:
        """Sync Kanban projections to Obsidian using configured board targets."""
        return self.sync_kanban_projections_with_mode(None)

    def sync_kanban_projections_with_mode(
        self, mode: Optional[str] = None
    ) -> List[str]:
        """
        Sync Kanban projections.
        mode values:
        - guide: writes to Guide - Kanban(.md) files only
        - prod: writes to main board files
        """
        resolved_mode = (
            (mode or os.getenv("OBSIDIAN_KANBAN_MODE", "prod")).strip().lower()
        )
        updated = []
        task_board_path, goals_board_path = self._resolve_kanban_board_paths(
            resolved_mode
        )
        guide_mode = resolved_mode == "guide"

        backlog_items, done_items = self._load_project_todo_items()
        done_events = self._get_today_done_events()
        for item in done_events:
            if item not in done_items:
                done_items.append(item)
        bridge = self._build_bridge_projection(backlog_items) if guide_mode else None
        task_board_content = self._generate_task_board(
            backlog_items, done_items, bridge=bridge
        )
        task_board_path.write_text(task_board_content)
        updated.append(str(task_board_path))

        goal_items = self._get_goal_events()
        if not goals_board_path.exists():
            goals_board_path.write_text(self._generate_goals_board())
        self._merge_goals_into_board(goals_board_path, goal_items)
        updated.append(str(goals_board_path))

        return updated

    def _resolve_kanban_board_paths(self, mode: str) -> Tuple[Path, Path]:
        """Resolve task/goals board paths based on sync mode."""
        if mode == "guide":
            return (
                self.kanban_path / "Guide - Kanban.md",
                self.kanban_path / "Guide - Kanban Goals.md",
            )

        task_candidates = [
            self.kanban_path / "Kanban.md",
            self.kanban_path / "Task Board.md",
        ]
        goals_candidates = [
            self.kanban_path / "Kanban Goals.md",
            self.kanban_path / "Goals Board.md",
        ]

        task_board = next(
            (p for p in task_candidates if p.exists()), task_candidates[1]
        )
        goals_board = next(
            (p for p in goals_candidates if p.exists()), goals_candidates[1]
        )
        return task_board, goals_board

    def _load_project_todo_items(self) -> Tuple[List[str], List[str]]:
        """Parse checked and unchecked tasks from Project-A TODO.md."""
        backlog = []
        done = []

        if not self.project_todo_path.exists():
            return backlog, done

        lines = self.project_todo_path.read_text().splitlines()
        pattern = re.compile(r"^\s*-\s*\[(\s*x\s*|\s*)\]\s*(.+)$", re.IGNORECASE)

        for line in lines:
            match = pattern.match(line)
            if not match:
                continue

            marker = match.group(1).strip().lower()
            item_text = match.group(2).strip()
            if not item_text:
                continue

            if marker == "x":
                done.append(item_text)
            else:
                backlog.append(item_text)

        return backlog, done

    def _get_today_done_events(self) -> List[str]:
        """Read today's DONE events from context DB for Kanban Done Today."""
        try:
            rows = self.repository.get_today_done_rows()
            items = []
            for activity, category in rows:
                if activity:
                    cat = category or "TASK"
                    items.append(
                        f"{activity.lower()} [category:: {cat.title()}] [source:: Event]"
                    )
            return items
        except Exception:
            return []

    def _generate_task_board(
        self,
        backlog_items: List[str],
        done_items: List[str],
        bridge: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        """Generate Kanban list board with your preferred columns."""
        return self.renderer.render_task_board(backlog_items, done_items, bridge)

    def _build_bridge_projection(
        self, backlog_items: List[str], lookback_days: int = 7
    ) -> Dict[str, List[str]]:
        """Bridge intent (manual backlog) and reality (event stream) for guide board."""
        try:
            rows = self.repository.get_bridge_rows(lookback_days)
            return self.projector.build_bridge_projection(rows, backlog_items)
        except Exception:
            return {"now": [], "paused": [], "captured": [], "next": []}

    def _generate_goals_board(self) -> str:
        """Generate goals Kanban board template."""
        return self.renderer.goals_board_template()

    def _get_goal_events(self) -> Dict[str, List[str]]:
        """Read GOAL events and map to goals board sections."""
        try:
            rows = self.repository.get_goal_rows()
            return self.projector.map_goal_events(rows)
        except Exception:
            return {
                "Short term": [],
                "Medium Term": [],
                "Long Term": [],
                "Come back to": [],
            }

    def _merge_goals_into_board(
        self, board_path: Path, goal_items: Dict[str, List[str]]
    ) -> None:
        """Merge new goal items into existing goals board sections without rewriting manual entries."""
        content = board_path.read_text()

        for section, items in goal_items.items():
            if not items:
                continue

            next_headers = [
                "## Short term",
                "## Medium Term",
                "## Long Term",
                "## Come back to",
                "%% kanban:settings",
            ]
            section_header = f"## {section}"
            start_idx = content.find(section_header)
            if start_idx == -1:
                continue

            end_idx = len(content)
            for header in next_headers:
                if header == section_header:
                    continue
                candidate = content.find(header, start_idx + len(section_header))
                if candidate != -1:
                    end_idx = min(end_idx, candidate)

            section_block = content[start_idx:end_idx]
            normalized_section_lines = {
                self._normalize_goal_line(line)
                for line in section_block.splitlines()
                if line.strip().startswith("- [")
            }
            append_lines = []
            for item in items:
                line = f"- [ ] {item}"
                if self._normalize_goal_line(line) not in normalized_section_lines:
                    append_lines.append(line)

            if not append_lines:
                continue

            insertion_point = end_idx
            content = (
                content[:insertion_point]
                + "\n"
                + "\n".join(append_lines)
                + "\n"
                + content[insertion_point:]
            )

        board_path.write_text(content)

    def _normalize_goal_line(self, line: str) -> str:
        """Normalize a goal line for dedup checks."""
        normalized = line.lower().strip()
        normalized = re.sub(r"^[-\s\[\]x]+", "", normalized)
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _get_today_events(self) -> List[Dict[str, Any]]:
        """Fetch today's events from SQLite"""
        try:
            return self.repository.get_today_events()
        except Exception as e:
            print(f"Error fetching events: {e}")
            return []

    def _get_all_dates(self) -> List[str]:
        """Get all unique dates from events"""
        try:
            return self.repository.get_all_dates()
        except Exception as e:
            print(f"Error fetching dates: {e}")
            return []

    def _get_events_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Fetch events for a specific date"""
        try:
            return self.repository.get_events_for_date(date)
        except Exception as e:
            print(f"Error fetching events for {date}: {e}")
            return []

    def _generate_note_content(
        self, date: datetime, events: List[Dict[str, Any]]
    ) -> str:
        """Generate Obsidian markdown content"""
        lines = [
            f"# {date.strftime('%Y-%m-%d %A')}",
            "",
            "## Activity Log",
            "",
        ]

        if not events:
            lines.append("*No activities logged today.*")
        else:
            for event in events:
                timestamp = event.get("timestamp", "")
                category = event.get("category", "UNKNOWN")
                activity = event.get("activity", "unknown")
                context = event.get("context", "")
                raw_input = event.get("raw_input", "")

                # Format time
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M")
                except:
                    time_str = "??"

                # Format event line
                event_line = f"- **{time_str}** "

                if category:
                    event_line += f"[[{category}]] "

                event_line += f"**{activity}**"

                if context:
                    event_line += f" ({context})"

                lines.append(event_line)

                # Add raw input as quote if different
                if raw_input and raw_input != f"{category} {activity}".strip():
                    lines.append(f"  > {raw_input}")

        # Add summary section
        lines.extend(
            [
                "",
                "## Summary",
                "",
                self._generate_summary(events),
                "",
                "---",
                "",
                f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
            ]
        )

        return "\n".join(lines)

    def _generate_summary(self, events: List[Dict[str, Any]]) -> str:
        """Generate summary statistics"""
        if not events:
            return "No activities."

        # Count by category
        categories = {}
        for event in events:
            cat = event.get("category", "UNKNOWN")
            categories[cat] = categories.get(cat, 0) + 1

        lines = [f"**Total activities:** {len(events)}"]

        if categories:
            lines.append("**Breakdown:**")
            for cat, count in sorted(
                categories.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"- {cat}: {count}")

        return "\n".join(lines)


if __name__ == "__main__":
    import sys

    sync = ObsidianSync()

    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        print("Syncing all events to Obsidian...")
        notes = sync.sync_all()
        print(f"Updated {len(notes)} daily notes")
        boards = sync.sync_kanban_projections_with_mode("prod")
        print(f"Updated {len(boards)} kanban boards")
    elif len(sys.argv) > 1 and sys.argv[1] == "--kanban":
        print("Syncing kanban projections...")
        boards = sync.sync_kanban_projections_with_mode("prod")
        for board in boards:
            print(f"Updated: {board}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--guide":
        print("Syncing guide kanban projections...")
        boards = sync.sync_kanban_projections_with_mode("guide")
        for board in boards:
            print(f"Updated: {board}")
    else:
        print("Syncing today's events...")
        note = sync.sync_today()
        print(f"Updated: {note}")
        boards = sync.sync_kanban_projections_with_mode(None)
        for board in boards:
            print(f"Updated: {board}")
