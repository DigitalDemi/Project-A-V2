"""
Event Parser - LLM-based natural language to structured event conversion
Follows the event-driven architecture: LLM is advisory only
"""

import re
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

try:
    from .parser_config import (
        Action,
        ACTION_PATTERNS,
        ACTIVITY_SKIP_WORDS,
        Category,
        CATEGORY_PATTERNS,
        GAME_KEYWORDS,
        GAME_NAMES,
    )
except ImportError:
    from parser_config import (
        Action,
        ACTION_PATTERNS,
        ACTIVITY_SKIP_WORDS,
        Category,
        CATEGORY_PATTERNS,
        GAME_KEYWORDS,
        GAME_NAMES,
    )


class EventParser:
    """
    Parses natural language into structured events
    Respects invariants: never writes directly to master.log, only suggests
    """

    # Valid event types from the architecture
    EVENT_TYPES = [
        "START",
        "DONE",
        "TASK",
        "THEORY",
        "PRACTICE",
        "GAME",
        "NOTE",
        "GOAL",
    ]

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

        # Special case: "valorant game" or "minecraft" - game names should be captured
        for word in words:
            clean = re.sub(r"[^\w\s-]", "", word).strip().lower()
            if clean in GAME_NAMES:
                return word

        # Special case: "for rust" or "session for rust" - look for words after 'for'
        if " for " in input_lower:
            parts = input_lower.split(" for ")
            if len(parts) > 1:
                after_for = parts[1].split()[0]
                clean = re.sub(r"[^\w\s-]", "", after_for).strip()
                if clean and clean not in ACTIVITY_SKIP_WORDS:
                    return clean

        # Special case: "database refactor" - look for compound nouns
        if len(words) >= 2:
            for i in range(len(words) - 1):
                word1 = re.sub(r"[^\w\s-]", "", words[i]).strip().lower()
                word2 = re.sub(r"[^\w\s-]", "", words[i + 1]).strip().lower()
                # If first word is not skip word and second is an action/process word
                if word1 not in ACTIVITY_SKIP_WORDS and word2 in {
                    "refactor",
                    "migration",
                    "update",
                    "build",
                    "code",
                }:
                    return words[i + 1]  # Return the action word

        # If category is specified, find the word before it
        if category:
            cat_lower = category.lower()
            for i, word in enumerate(words):
                if cat_lower in word.lower() and i > 0:
                    # Return the word before the category
                    prev_word = words[i - 1]
                    clean = re.sub(r"[^\w\s-]", "", prev_word).strip()
                    if clean and clean.lower() not in ACTIVITY_SKIP_WORDS:
                        return clean

        # Find the first significant word (not in skip_words)
        for word in words:
            clean = re.sub(r"[^\w\s-]", "", word).strip()
            clean_lower = clean.lower()
            if clean and clean_lower not in ACTIVITY_SKIP_WORDS:
                # Check if it's not a category word itself
                is_category = clean_lower in ["theory", "practice", "game", "task"]
                if not is_category:
                    return clean

        # Fallback: return first non-skip word
        for word in words:
            clean = re.sub(r"[^\w\s-]", "", word).strip()
            if clean and clean.lower() not in ACTIVITY_SKIP_WORDS:
                return clean

        # Ultimate fallback: last word that's not punctuation
        for word in reversed(words):
            clean = re.sub(r"[^\w\s-]", "", word).strip()
            if clean:
                return clean

        return "unknown"

    def _extract_goal_payload(self, input_text: str) -> Tuple[str, Optional[str], bool]:
        """
        Extract goal activity and horizon from natural text.
        Returns (activity_slug, horizon, has_payload).
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

        has_payload = bool(cleaned)

        if not cleaned:
            cleaned = ""

        activity_slug = re.sub(r"[^a-z0-9\s_-]", "", cleaned)
        activity_slug = activity_slug.replace(" ", "_")
        if not activity_slug:
            activity_slug = ""

        return activity_slug.upper(), horizon, has_payload

    def parse_with_rules(self, input_text: str) -> Dict[str, Any]:
        """
        Rule-based parsing as fallback/initial implementation
        Maintains the invariant: returns suggestion, doesn't write
        """
        input_lower = input_text.lower()

        # Determine action
        action = "start"  # default
        for act, patterns in ACTION_PATTERNS.items():
            if any(p in input_lower for p in patterns):
                action = act.value
                break

        # Determine category
        category = None
        if "goal" in input_lower or "goals" in input_lower:
            category = "GOAL"
        elif self._is_game_intent(input_lower):
            category = "GAME"
        for cat, patterns in CATEGORY_PATTERNS.items():
            if category in {"GOAL", "GAME"}:
                break
            if any(p in input_lower for p in patterns):
                category = cat.value.upper()
                break

        # Extract activity (improved - finds the main subject)
        if category == "GOAL":
            activity, goal_horizon, has_goal_payload = self._extract_goal_payload(
                input_text
            )
        else:
            activity = self._extract_activity(input_text, category)
            goal_horizon = None
            has_goal_payload = True

        # Clean up activity name
        activity = re.sub(r"[^\w\s-]", "", activity).strip()

        # Extract context (everything after activity or in quotes)
        context = None
        if '"' in input_text:
            match = re.search(r'"([^"]+)"', input_text)
            if match:
                context = match.group(1)

        if goal_horizon and not context:
            context = goal_horizon

        if category == "GOAL" and not has_goal_payload:
            return {
                "action": action,
                "category": "GOAL",
                "activity": "",
                "context": goal_horizon,
                "raw_input": input_text,
                "confidence": 0.0,
                "method": "rule_based",
                "needs_clarification": True,
                "clarification_message": (
                    "Please include your goal text. "
                    "Example: add goal short term learn japanese"
                ),
            }

        return {
            "action": action,
            "category": category or "TASK",  # default
            "activity": activity.upper(),
            "context": context,
            "raw_input": input_text,
            "confidence": 0.7,  # rule-based confidence
            "method": "rule_based",
        }

    def _is_game_intent(self, input_lower: str) -> bool:
        words = {
            re.sub(r"[^a-z0-9_-]", "", token)
            for token in input_lower.split()
            if token.strip()
        }
        explicit_game_cues = {"game", "gaming", "play", "playing"}
        if words & explicit_game_cues:
            return True

        non_game_category_words = (
            CATEGORY_PATTERNS[Category.THEORY]
            | CATEGORY_PATTERNS[Category.PRACTICE]
            | CATEGORY_PATTERNS[Category.TASK]
        )
        if words & non_game_category_words:
            return False

        if words & GAME_NAMES:
            return True

        return any(keyword in input_lower for keyword in explicit_game_cues)

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
        if parsed.get("needs_clarification"):
            return ""

        action = parsed["action"].upper()
        category = parsed["category"].upper()
        activity = parsed["activity"].upper()

        # Handle different event formats based on action
        if action == "NOTE":
            return f"NOTE {activity}"
        elif action == "DONE":
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
        result["formatted_event"] = self.format_event(result)
        result["timestamp"] = datetime.now().isoformat()

        return result


if __name__ == "__main__":
    parser = EventParser()

    # Test cases
    test_inputs = [
        "Started working on pandas theory",
        "Done with the database refactor",
        "Beginning practice session for rust",
        "Note: pytorch data loaders are tricky",
    ]

    for text in test_inputs:
        result = parser.parse(text)
        print(f"Input: {text}")
        print(f"Parsed: {result}")
        print(f"Event: {result['formatted_event']}")
        print("---")
