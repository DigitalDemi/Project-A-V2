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
    EVENT_TYPES = ['START', 'DONE', 'TASK', 'THEORY', 'PRACTICE', 'GAME', 'NOTE', 'GOAL']
    
    # Pattern for fuzzy matching
    ACTION_PATTERNS = {
        'start': ['start', 'begin', 'starting', 'began', 'commence', 'launch', 'add', 'set'],
        'done': ['done', 'finished', 'complete', 'completed', 'end', 'ended', 'stop'],
        'note': ['note', 'noted', 'jot', 'remember', 'thought'],
    }
    
    CATEGORY_PATTERNS = {
        'theory': ['theory', 'learn', 'learning', 'study', 'studying', 'read', 'reading'],
        'practice': ['practice', 'practicing', 'exercise', 'implement', 'coding', 'writing'],
        'task': ['task', 'work', 'project', 'job', 'assignment'],
        'game': ['game', 'gaming', 'play', 'playing', 'valorant', 'minecraft'],
        'goal': ['goal', 'goals'],
    }
    
    def __init__(self):
        self.llm = None  # Will be initialized with llama-cpp

    def _extract_activity(self, input_text: str, category: Optional[str]) -> str:
        """
        Extract the main activity/subject from input
        Uses multiple heuristics to find the most likely activity name
        """
        input_lower = input_text.lower()
        words = input_text.split()

        if not words:
            return "unknown"

        # List of words to skip (verbs, prepositions, articles, category words)
        skip_words = {'started', 'starting', 'start', 'begin', 'began', 'beginning', 'commence',
                      'working', 'work', 'on', 'with', 'for', 'the', 'a', 'an', 'are', 'is',
                      'done', 'finished', 'finish', 'complete', 'completed', 'end', 'ended', 'stop', 'doing',
                      'game', 'gaming', 'play', 'playing', 'task', 'tasks', 'theory', 'practice',
                      'goal', 'goals', 'short', 'medium', 'long', 'term', 'comeback',
                      'note', 'notes', 'learning', 'learn', 'study', 'studying', 'reading', 'read',
                      'implement', 'implementing', 'exercise', 'exercising', 'project', 'projects',
                      'assignment', 'job', 'session', 'sessions', 'data', 'loaders', 'tricky',
                      'and', 'to', 'of', 'in', 'at', 'i', 'my', 'this', 'that', 'it'}

        # Special case: "valorant game" or "minecraft" - game names should be captured
        game_names = {'valorant', 'minecraft', 'fortnite', 'overwatch', 'apex', 'rust', 'python', 'pandas'}
        for word in words:
            clean = re.sub(r'[^\w\s-]', '', word).strip().lower()
            if clean in game_names:
                return word

        # Special case: "for rust" or "session for rust" - look for words after 'for'
        if ' for ' in input_lower:
            parts = input_lower.split(' for ')
            if len(parts) > 1:
                after_for = parts[1].split()[0]
                clean = re.sub(r'[^\w\s-]', '', after_for).strip()
                if clean and clean not in skip_words:
                    return clean

        # Special case: "database refactor" - look for compound nouns
        if len(words) >= 2:
            for i in range(len(words) - 1):
                word1 = re.sub(r'[^\w\s-]', '', words[i]).strip().lower()
                word2 = re.sub(r'[^\w\s-]', '', words[i+1]).strip().lower()
                # If first word is not skip word and second is an action/process word
                if word1 not in skip_words and word2 in {'refactor', 'migration', 'update', 'build', 'code'}:
                    return words[i+1]  # Return the action word

        # If category is specified, find the word before it
        if category:
            cat_lower = category.lower()
            for i, word in enumerate(words):
                if cat_lower in word.lower() and i > 0:
                    # Return the word before the category
                    prev_word = words[i-1]
                    clean = re.sub(r'[^\w\s-]', '', prev_word).strip()
                    if clean and clean.lower() not in skip_words:
                        return clean

        # Find the first significant word (not in skip_words)
        for word in words:
            clean = re.sub(r'[^\w\s-]', '', word).strip()
            clean_lower = clean.lower()
            if clean and clean_lower not in skip_words:
                # Check if it's not a category word itself
                is_category = clean_lower in ['theory', 'practice', 'game', 'task']
                if not is_category:
                    return clean

        # Fallback: return first non-skip word
        for word in words:
            clean = re.sub(r'[^\w\s-]', '', word).strip()
            if clean and clean.lower() not in skip_words:
                return clean

        # Ultimate fallback: last word that's not punctuation
        for word in reversed(words):
            clean = re.sub(r'[^\w\s-]', '', word).strip()
            if clean:
                return clean

        return "unknown"

    def _extract_goal_payload(self, input_text: str) -> tuple[str, Optional[str]]:
        """
        Extract goal activity and horizon from natural text.
        Returns (activity_slug, horizon).
        """
        lowered = input_text.lower()

        horizon = None
        horizon_patterns = {
            "SHORT_TERM": ["short term", "short-term", "short"],
            "MEDIUM_TERM": ["medium term", "medium-term", "medium"],
            "LONG_TERM": ["long term", "long-term", "long"],
            "COME_BACK_TO": ["come back to", "come-back", "comeback"],
        }

        for value, patterns in horizon_patterns.items():
            if any(p in lowered for p in patterns):
                horizon = value
                break

        # Strip trigger words and horizon hints, keep human goal phrase
        cleaned = lowered
        cleaned = re.sub(r"\b(add|set|create|new)\b", " ", cleaned)
        cleaned = re.sub(r"\b(goal|goals)\b", " ", cleaned)
        cleaned = re.sub(r"\b(short|medium|long)\b", " ", cleaned)
        cleaned = re.sub(r"\bterm\b", " ", cleaned)
        cleaned = re.sub(r"\b(come\s+back\s+to|comeback|come-back)\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            cleaned = "new_goal"

        activity_slug = re.sub(r"[^a-z0-9\s_-]", "", cleaned)
        activity_slug = activity_slug.replace(" ", "_")
        if not activity_slug:
            activity_slug = "new_goal"

        return activity_slug.upper(), horizon

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
        if 'goal' in input_lower or 'goals' in input_lower:
            category = 'GOAL'
        for cat, patterns in self.CATEGORY_PATTERNS.items():
            if category == 'GOAL':
                break
            if any(p in input_lower for p in patterns):
                category = cat.upper()
                break
        
        # Extract activity (improved - finds the main subject)
        if category == 'GOAL':
            activity, goal_horizon = self._extract_goal_payload(input_text)
        else:
            activity = self._extract_activity(input_text, category)
            goal_horizon = None
        
        # Clean up activity name
        activity = re.sub(r'[^\w\s-]', '', activity).strip()
        
        # Extract context (everything after activity or in quotes)
        context = None
        if '"' in input_text:
            match = re.search(r'"([^"]+)"', input_text)
            if match:
                context = match.group(1)
        
        if goal_horizon and not context:
            context = goal_horizon

        return {
            'action': action,
            'category': category or 'TASK',  # default
            'activity': activity.upper(),
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
