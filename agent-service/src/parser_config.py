from enum import StrEnum


class Action(StrEnum):
    START = "start"
    DONE = "done"
    NOTE = "note"


class Category(StrEnum):
    THEORY = "theory"
    PRACTICE = "practice"
    TASK = "task"
    GAME = "game"
    GOAL = "goal"


GAME_NAMES = {"valorant", "minecraft", "fortnite", "overwatch", "apex", "rust"}
GAME_KEYWORDS = {"game", "gaming", "play", "playing"} | GAME_NAMES

ACTION_PATTERNS = {
    Action.START: {
        "start",
        "begin",
        "starting",
        "began",
        "commence",
        "launch",
        "add",
        "set",
    },
    Action.DONE: {"done", "finished", "complete", "completed", "end", "ended", "stop"},
    Action.NOTE: {"note", "noted", "jot", "remember", "thought"},
}

CATEGORY_PATTERNS = {
    Category.THEORY: {
        "theory",
        "learn",
        "learning",
        "study",
        "studying",
        "read",
        "reading",
    },
    Category.PRACTICE: {
        "practice",
        "practicing",
        "exercise",
        "implement",
        "coding",
        "writing",
    },
    Category.TASK: {"task", "work", "project", "job", "assignment"},
    Category.GAME: GAME_KEYWORDS,
    Category.GOAL: {"goal", "goals"},
}

_STOP_WORDS = {
    "on",
    "with",
    "for",
    "the",
    "a",
    "an",
    "are",
    "is",
    "doing",
    "and",
    "to",
    "of",
    "in",
    "at",
    "i",
    "my",
    "this",
    "that",
    "it",
    "am",
    "im",
    "i'm",
    "now",
    "currently",
    "just",
}

_INFLECTED_ACTION_WORDS = {
    "started",
    "beginning",
    "finished",
    "ended",
    "stopped",
    "completing",
}

ACTIVITY_SKIP_WORDS = (
    ACTION_PATTERNS[Action.START]
    | ACTION_PATTERNS[Action.DONE]
    | ACTION_PATTERNS[Action.NOTE]
    | GAME_KEYWORDS
    | {word for words in CATEGORY_PATTERNS.values() for word in words}
    | _STOP_WORDS
    | _INFLECTED_ACTION_WORDS
)
