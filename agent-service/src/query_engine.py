"""
Query Engine - Complex analytics and insights from event log
Respects invariants: only reads, never writes
"""
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

class QueryEngine:
    """
    Handles complex queries by analyzing event log + context
    Never modifies master.log, only derives projections
    """
    
    def __init__(self, db_path: str = "data/context.db", log_path: str = "../Project-A/log/master.log"):
        self.db_path = db_path
        self.log_path = log_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database for context storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Events table - rich metadata (not the source of truth)
        cursor.execute('''
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
        ''')
        
        # LLM decisions for training
        cursor.execute('''
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
        ''')
        
        # Derived sessions (projection)
        cursor.execute('''
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
        ''')
        
        conn.commit()
        conn.close()
    
    def read_master_log(self) -> List[str]:
        """Read master.log - source of truth"""
        try:
            with open(self.log_path, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            return []
    
    def derive_sessions(self) -> List[Dict[str, Any]]:
        """
        Derive sessions from event log
        Session = period between START events
        """
        events = self.read_master_log()
        sessions = []
        current_session = None
        
        for i, event_line in enumerate(events):
            parts = event_line.split()
            if len(parts) >= 3 and parts[0] == 'START':
                # End previous session
                if current_session:
                    current_session['end_event_index'] = i - 1
                    sessions.append(current_session)
                
                # Start new session
                current_session = {
                    'category': parts[1],
                    'activity': parts[2],
                    'start_event_index': i,
                    'raw_line': event_line
                }
        
        # Don't forget last session
        if current_session:
            current_session['end_event_index'] = len(events) - 1
            sessions.append(current_session)
        
        return sessions
    
    def calculate_ratios(self, timeframe: str = 'week') -> Dict[str, Any]:
        """
        Calculate theory to practice ratios
        Timeframe: 'day', 'week', 'month'
        """
        sessions = self.derive_sessions()
        
        counts = {
            'THEORY': 0,
            'PRACTICE': 0,
            'TASK': 0,
            'GAME': 0
        }
        
        for session in sessions:
            cat = session.get('category', 'UNKNOWN')
            if cat in counts:
                counts[cat] += 1
        
        total = sum(counts.values())
        if total == 0:
            return {'error': 'No data available'}
        
        return {
            'timeframe': timeframe,
            'total_sessions': total,
            'breakdown': counts,
            'ratios': {
                cat: round(count / total * 100, 1) 
                for cat, count in counts.items()
            },
            'theory_to_practice': round(
                counts['THEORY'] / max(counts['PRACTICE'], 1), 2
            )
        }
    
    def answer_query(self, query: str) -> Dict[str, Any]:
        """
        Answer natural language queries
        Examples:
        - "What did I work on yesterday?"
        - "Theory to practice ratio this week?"
        - "How much time on pandas?"
        """
        query_lower = query.lower()
        
        # Pattern matching for query types
        if 'ratio' in query_lower:
            return {
                'type': 'ratio',
                'answer': self.calculate_ratios()
            }
        
        elif 'yesterday' in query_lower or 'last' in query_lower:
            sessions = self.derive_sessions()
            return {
                'type': 'timeline',
                'answer': {
                    'recent_sessions': sessions[-5:] if sessions else [],
                    'count': len(sessions)
                }
            }
        
        elif 'what did i' in query_lower or 'work on' in query_lower:
            sessions = self.derive_sessions()
            activities = list(set(s['activity'] for s in sessions))
            return {
                'type': 'summary',
                'answer': {
                    'activities': activities,
                    'total_activities': len(activities)
                }
            }
        
        else:
            return {
                'type': 'unknown',
                'answer': 'I can tell you about your ratios, recent work, or activity summary. What would you like to know?'
            }
    
    def store_context(self, event_data: Dict[str, Any]):
        """Store rich context in SQLite (not master.log)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO events 
            (timestamp, event_type, category, activity, context, raw_input, user_confirmed, log_position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_data.get('timestamp'),
            event_data.get('action'),
            event_data.get('category'),
            event_data.get('activity'),
            event_data.get('context'),
            event_data.get('raw_input'),
            event_data.get('user_confirmed', False),
            event_data.get('log_position')
        ))
        
        conn.commit()
        conn.close()
    
    def store_llm_decision(self, decision: Dict[str, Any]):
        """Store LLM decision for future training"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO llm_decisions 
            (timestamp, user_input, llm_suggestion, user_response, confidence, model)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            decision.get('timestamp'),
            decision.get('user_input'),
            decision.get('llm_suggestion'),
            decision.get('user_response'),
            decision.get('confidence'),
            decision.get('model', 'qwen-2.5-3b')
        ))
        
        conn.commit()
        conn.close()

if __name__ == '__main__':
    engine = QueryEngine()
    
    # Test queries
    print("Testing query engine...")
    print("Sessions:", engine.derive_sessions())
    print("Ratios:", engine.calculate_ratios())
    print("Query 'what did I work on':", engine.answer_query("what did I work on"))
