"""
Obsidian Sync - Updates Obsidian vault from event log
One-way sync: log → Obsidian (projection layer)
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

class ObsidianSync:
    """
    Syncs event data to Obsidian vault
    Creates/updates daily notes with activity logs
    """
    
    def __init__(self, vault_path: str = "~/vaults/personal", db_path: str = "../agent-service/data/context.db"):
        self.vault_path = Path(vault_path).expanduser()
        self.db_path = db_path
        self.daily_notes_path = self.vault_path / "Daily"
        
        # Ensure directories exist
        self.daily_notes_path.mkdir(parents=True, exist_ok=True)
    
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
    else:
        print("Syncing today's events...")
        note = sync.sync_today()
        print(f"Updated: {note}")
