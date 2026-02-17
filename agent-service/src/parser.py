"""
Event Parser - LLM-based natural language to structured event conversion
Follows the event-driven architecture: LLM is advisory only
"""
import json
import re
from typing import Optional, Dict, Any
from datetime import datetime

class EventParser:
    """
    Parses natural language into structured events
    Respects invariants: never writes directly to master.log, only suggests
    """
    
    # Valid event types from the architecture
    EVENT_TYPES = ['START', 'DONE', 'TASK', 'THEORY', 'PRACTICE', 'GAME', 'NOTE']
    
    # Pattern for fuzzy matching
    ACTION_PATTERNS = {
        'start': ['start', 'begin', 'starting', 'began', 'commence', 'launch'],
        'done': ['done', 'finished', 'complete', 'completed', 'end', 'ended', 'stop'],
        'note': ['note', 'noted', 'jot', 'remember', 'thought'],
    }
    
    CATEGORY_PATTERNS = {
        'theory': ['theory', 'learn', 'learning', 'study', 'studying', 'read', 'reading'],
        'practice': ['practice', 'practicing', 'exercise', 'implement', 'coding', 'writing'],
        'task': ['task', 'work', 'project', 'job', 'assignment'],
        'game': ['game', 'gaming', 'play', 'playing', 'valorant', 'minecraft'],
    }
    
    def __init__(self):
        self.llm = None  # Will be initialized with llama-cpp
        
    def parse_with_rules(self, input_text: str) -> Dict[str, Any]:
        """
        Rule-based parsing as fallback/initial implementation
        Maintains the invariant: returns suggestion, doesn't write
        """
        input_lower = input_text.lower()
        
        # Determine action
        action = 'start'  # default
        for act, patterns in self.ACTION_PATTERNS.items():
            if any(p in input_lower for p in patterns):
                action = act
                break
        
        # Determine category
        category = None
        for cat, patterns in self.CATEGORY_PATTERNS.items():
            if any(p in input_lower for p in patterns):
                category = cat.upper()
                break
        
        # Extract activity (simplified - takes last significant word)
        words = input_text.split()
        activity = words[-1] if words else "unknown"
        
        # Clean up activity name
        activity = re.sub(r'[^\w\s-]', '', activity).strip()
        
        # Extract context (everything after activity or in quotes)
        context = None
        if '"' in input_text:
            match = re.search(r'"([^"]+)"', input_text)
            if match:
                context = match.group(1)
        
        return {
            'action': action,
            'category': category or 'TASK',  # default
            'activity': activity,
            'context': context,
            'raw_input': input_text,
            'confidence': 0.7,  # rule-based confidence
            'method': 'rule_based'
        }
    
    def parse_with_llm(self, input_text: str) -> Dict[str, Any]:
        """
        LLM-based parsing (placeholder for when model is loaded)
        Will use local Qwen 2.5 3B via llama-cpp
        """
        if self.llm is None:
            return self.parse_with_rules(input_text)
        
        # TODO: Implement actual LLM inference
        # This will use llama-cpp-python to run quantized model
        prompt = f"""Parse this activity description into structured event.

Input: "{input_text}"

Rules:
- Actions: start, done, note
- Categories: THEORY, PRACTICE, TASK, GAME
- Activity: main subject (1-3 words)
- Context: optional details

Output JSON:
{{
  "action": "...",
  "category": "...",
  "activity": "...",
  "context": "..."
}}

Response:"""
        
        # Placeholder - will implement actual LLM call
        return self.parse_with_rules(input_text)
    
    def format_event(self, parsed: Dict[str, Any]) -> str:
        """
        Format parsed data into canonical event string
        Returns format like: "START THEORY pandas"
        """
        action = parsed['action'].upper()
        category = parsed['category'].upper()
        activity = parsed['activity'].upper()
        
        # Handle different event formats based on action
        if action == 'NOTE':
            return f"NOTE {activity}"
        elif action == 'DONE':
            return f"DONE {category} {activity}"
        else:  # START is default
            return f"START {category} {activity}"
    
    def parse(self, input_text: str, use_llm: bool = False) -> Dict[str, Any]:
        """
        Main parsing entry point
        Returns suggestion that user must confirm
        """
        if use_llm and self.llm is not None:
            result = self.parse_with_llm(input_text)
        else:
            result = self.parse_with_rules(input_text)
        
        # Add formatted event string
        result['formatted_event'] = self.format_event(result)
        result['timestamp'] = datetime.now().isoformat()
        
        return result

if __name__ == '__main__':
    parser = EventParser()
    
    # Test cases
    test_inputs = [
        "Started working on pandas theory",
        "Done with the database refactor",
        "Beginning practice session for rust",
        "Note: pytorch data loaders are tricky"
    ]
    
    for text in test_inputs:
        result = parser.parse(text)
        print(f"Input: {text}")
        print(f"Parsed: {result}")
        print(f"Event: {result['formatted_event']}")
        print("---")
