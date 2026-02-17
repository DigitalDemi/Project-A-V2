"""
Obsidian Sync - Updates Obsidian vault from event log
One-way sync: log → Obsidian (projection layer)
"""
import sqlite3
import re
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv

class ObsidianSync:
    """
    Syncs event data to Obsidian vault
    Creates/updates daily notes with activity logs
    """
    
    def __init__(self, vault_path: Optional[str] = None, db_path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent
        load_dotenv(base_dir / ".env")

        resolved_vault = vault_path or os.getenv("OBSIDIAN_VAULT_PATH", "~/vaults/personal")
        self.vault_path = Path(resolved_vault).expanduser()
        self.db_path = str(Path(db_path)) if db_path else str(base_dir / "agent-service" / "data" / "context.db")
        self.project_todo_path = base_dir.parent / "Project-A" / "TODO.md"
        self.daily_notes_path = self.vault_path / "Daily"
        self.kanban_path = self.vault_path / "Kanban"
        
        # Ensure directories exist
        self.daily_notes_path.mkdir(parents=True, exist_ok=True)
        self.kanban_path.mkdir(parents=True, exist_ok=True)
    
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
            
            content = self._generate_note_content(datetime.strptime(date, '%Y-%m-%d'), events)
            note_path.write_text(content)
            updated_notes.append(str(note_path))
        
        return updated_notes

    def sync_kanban_projections(self) -> List[str]:
        """Sync Kanban projections to Obsidian using Project-A TODO and goals template."""
        updated = []
        task_board_path = self.kanban_path / "Task Board.md"
        goals_board_path = self.kanban_path / "Goals Board.md"

        backlog_items, done_items = self._load_project_todo_items()
        done_events = self._get_today_done_events()
        for item in done_events:
            if item not in done_items:
                done_items.append(item)
        task_board_content = self._generate_task_board(backlog_items, done_items)
        task_board_path.write_text(task_board_content)
        updated.append(str(task_board_path))

        goal_items = self._get_goal_events()
        if not goals_board_path.exists():
            goals_board_path.write_text(self._generate_goals_board())
        self._merge_goals_into_board(goals_board_path, goal_items)
        updated.append(str(goals_board_path))

        return updated

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
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute(
                '''
                SELECT activity, category
                FROM events
                WHERE date(timestamp) = date(?)
                  AND lower(event_type) = 'done'
                ORDER BY timestamp
                ''',
                (today,),
            )
            rows = cursor.fetchall()
            conn.close()
            items = []
            for activity, category in rows:
                if activity:
                    cat = category or "TASK"
                    items.append(f"{activity.lower()} [category:: {cat.title()}] [source:: Event]")
            return items
        except Exception:
            return []

    def _generate_task_board(self, backlog_items: List[str], done_items: List[str]) -> str:
        """Generate Kanban list board with your preferred columns."""
        def task_lines(items: List[str], checked: bool = False) -> List[str]:
            if not items:
                return ["- [ ]"] if not checked else ["- [x]"]
            mark = "x" if checked else " "
            return [f"- [{mark}] {item}" for item in items]

        lines = [
            "---",
            "kanban-plugin: list",
            "---",
            "",
            "## Focus",
            "",
            "",
            "## Creative",
            "",
            "",
            "## Light",
            "",
            "",
            "## Recovery",
            "",
            "",
            "## Reflect",
            "",
            "",
            "## Backlog",
        ]

        lines.extend(task_lines(backlog_items, checked=False))
        lines.extend([
            "",
            "## Reconsider",
            "- [ ]",
            "",
            "## Done Today",
        ])
        lines.extend(task_lines(done_items, checked=True))
        lines.extend([
            "",
            "## Admin",
            "- [ ]",
            "",
            "",
            "%% kanban:settings",
            "```",
            '{"kanban-plugin":"list","list-collapse":[false,null,false,false,false,false]}',
            "```",
            "%%",
            "",
        ])
        return "\n".join(lines)

    def _generate_goals_board(self) -> str:
        """Generate goals Kanban board template."""
        return """---
kanban-plugin: board
---

## Short term

- [ ] Learn Music theory
- [ ] Build my Personal Brand [[Personal Youtube]]
- [ ] Build Some projects for each discipline Computer science
- [ ] Learning Russian
- [ ] Learn to drive
- [ ] Learn testing
- [ ] CCNA
- [ ] Learn japense
- [ ] Theory Vs practice bot


## Medium Term

- [ ] Find a Junior development Job
- [ ] Save for buying a house
- [ ] Saving for staying in an apartment in a good area


## Long Term

- [ ] Move to mid-level position
- [ ] Earn 10k month
- [ ] Build A security fund


## Come back to

- [ ] Fix up website to put learning
- [ ] Finish the Market analysis bot to find hosuing




%% kanban:settings
```
{"kanban-plugin":"board","list-collapse":[false,false,false,false]}
```
%%
"""

    def _get_goal_events(self) -> Dict[str, List[str]]:
        """Read GOAL events and map to goals board sections."""
        section_map: Dict[str, List[str]] = {
            "Short term": [],
            "Medium Term": [],
            "Long Term": [],
            "Come back to": [],
        }

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT activity, context, raw_input
                FROM events
                WHERE upper(category) = 'GOAL'
                ORDER BY timestamp
                '''
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return section_map

        for activity, context, raw_input in rows:
            text = self._goal_display_text(activity, raw_input)
            section = self._goal_section_from_context(context)
            if text and text not in section_map[section]:
                section_map[section].append(text)

        return section_map

    def _goal_section_from_context(self, context: Optional[str]) -> str:
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

    def _goal_display_text(self, activity: Optional[str], raw_input: Optional[str]) -> str:
        if raw_input:
            cleaned = re.sub(r"\b(add|set|create|new)\b", "", raw_input, flags=re.IGNORECASE)
            cleaned = re.sub(r"\b(goal|goals)\b", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\b(short|medium|long)\s*-?\s*term\b", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\bcome\s+back\s+to\b", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
            if cleaned:
                return cleaned

        if activity:
            return activity.replace("_", " ").title()

        return ""

    def _merge_goals_into_board(self, board_path: Path, goal_items: Dict[str, List[str]]) -> None:
        """Merge new goal items into existing goals board sections without rewriting manual entries."""
        content = board_path.read_text()

        for section, items in goal_items.items():
            if not items:
                continue

            next_headers = ["## Short term", "## Medium Term", "## Long Term", "## Come back to", "%% kanban:settings"]
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
            append_lines = []
            for item in items:
                line = f"- [ ] {item}"
                if line not in section_block:
                    append_lines.append(line)

            if not append_lines:
                continue

            insertion_point = end_idx
            content = content[:insertion_point] + "\n" + "\n".join(append_lines) + "\n" + content[insertion_point:]

        board_path.write_text(content)
    
    def _get_today_events(self) -> List[Dict[str, Any]]:
        """Fetch today's events from SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('''
                SELECT timestamp, event_type, category, activity, context, raw_input
                FROM events
                WHERE date(timestamp) = date(?)
                ORDER BY timestamp
            ''', (today,))
            
            columns = [desc[0] for desc in cursor.description]
            events = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            conn.close()
            return events
        except Exception as e:
            print(f"Error fetching events: {e}")
            return []
    
    def _get_all_dates(self) -> List[str]:
        """Get all unique dates from events"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT date(timestamp) as date
                FROM events
                ORDER BY date
            ''')
            
            dates = [row[0] for row in cursor.fetchall()]
            conn.close()
            return dates
        except Exception as e:
            print(f"Error fetching dates: {e}")
            return []
    
    def _get_events_for_date(self, date: str) -> List[Dict[str, Any]]:
        """Fetch events for a specific date"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, event_type, category, activity, context, raw_input
                FROM events
                WHERE date(timestamp) = date(?)
                ORDER BY timestamp
            ''', (date,))
            
            columns = [desc[0] for desc in cursor.description]
            events = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            conn.close()
            return events
        except Exception as e:
            print(f"Error fetching events for {date}: {e}")
            return []
    
    def _generate_note_content(self, date: datetime, events: List[Dict[str, Any]]) -> str:
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
                timestamp = event.get('timestamp', '')
                category = event.get('category', 'UNKNOWN')
                activity = event.get('activity', 'unknown')
                context = event.get('context', '')
                raw_input = event.get('raw_input', '')
                
                # Format time
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = '??'
                
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
        lines.extend([
            "",
            "## Summary",
            "",
            self._generate_summary(events),
            "",
            "---",
            "",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        ])
        
        return '\n'.join(lines)
    
    def _generate_summary(self, events: List[Dict[str, Any]]) -> str:
        """Generate summary statistics"""
        if not events:
            return "No activities."
        
        # Count by category
        categories = {}
        for event in events:
            cat = event.get('category', 'UNKNOWN')
            categories[cat] = categories.get(cat, 0) + 1
        
        lines = [f"**Total activities:** {len(events)}"]
        
        if categories:
            lines.append("**Breakdown:**")
            for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {cat}: {count}")
        
        return '\n'.join(lines)

if __name__ == '__main__':
    import sys
    
    sync = ObsidianSync()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--all':
        print("Syncing all events to Obsidian...")
        notes = sync.sync_all()
        print(f"Updated {len(notes)} daily notes")
        boards = sync.sync_kanban_projections()
        print(f"Updated {len(boards)} kanban boards")
    elif len(sys.argv) > 1 and sys.argv[1] == '--kanban':
        print("Syncing kanban projections...")
        boards = sync.sync_kanban_projections()
        for board in boards:
            print(f"Updated: {board}")
    else:
        print("Syncing today's events...")
        note = sync.sync_today()
        print(f"Updated: {note}")
        boards = sync.sync_kanban_projections()
        for board in boards:
            print(f"Updated: {board}")
