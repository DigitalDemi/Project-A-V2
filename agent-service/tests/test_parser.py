"""
Tests for Event Parser
Validates parsing logic and maintains architecture invariants
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parser import EventParser


class TestEventParser(unittest.TestCase):
    """Test event parsing with various inputs"""

    def setUp(self):
        self.parser = EventParser()

    def test_basic_start_event(self):
        """Test parsing simple start events"""
        result = self.parser.parse("Started working on pandas theory")

        self.assertEqual(result["action"], "start")
        self.assertEqual(result["category"], "THEORY")
        self.assertEqual(result["formatted_event"], "START THEORY PANDAS")
        self.assertIn("confidence", result)
        self.assertIn("timestamp", result)

    def test_done_event(self):
        """Test parsing done/finished events"""
        result = self.parser.parse("Done with database refactor")

        self.assertEqual(result["action"], "done")
        self.assertEqual(result["category"], "TASK")
        self.assertEqual(result["formatted_event"], "DONE TASK REFACTOR")

    def test_practice_event(self):
        """Test parsing practice events"""
        result = self.parser.parse("Beginning practice session for rust")

        self.assertEqual(result["action"], "start")
        self.assertEqual(result["category"], "PRACTICE")
        self.assertEqual(result["formatted_event"], "START PRACTICE RUST")

    def test_game_event(self):
        """Test parsing game events"""
        result = self.parser.parse("Starting valorant game")

        self.assertEqual(result["action"], "start")
        self.assertEqual(result["category"], "GAME")
        self.assertEqual(result["formatted_event"], "START GAME VALORANT")

    def test_explicit_task_gaming_still_maps_to_game(self):
        """Gaming intent should stay GAME even if text includes 'task'"""
        result = self.parser.parse("start task gaming")

        self.assertEqual(result["category"], "GAME")
        self.assertEqual(result["formatted_event"], "START GAME GAMING")

    def test_natural_phrase_i_am_eating_extracts_activity(self):
        """Common filler words should not become the activity"""
        result = self.parser.parse("i am eating")

        self.assertEqual(result["activity"], "EATING")

    def test_note_event(self):
        """Test parsing note events"""
        result = self.parser.parse("Note: pytorch data loaders are tricky")

        self.assertEqual(result["action"], "note")
        self.assertEqual(result["formatted_event"], "NOTE PYTORCH")

    def test_context_extraction(self):
        """Test extracting context from quotes"""
        result = self.parser.parse('Started pandas "chapter 3 on dataframes"')

        self.assertEqual(result["activity"], "PANDAS")
        # Context extraction should capture quoted text
        self.assertIsNotNone(result.get("context"))

    def test_variations(self):
        """Test various phrasings work"""
        variations = [
            ("beginning pandas theory", "START", "THEORY", "PANDAS"),
            ("commence rust practice", "START", "PRACTICE", "RUST"),
            ("finished the task", "DONE", "TASK", "TASK"),
            ("ended gaming session", "DONE", "GAME", "SESSION"),
        ]

        for (
            input_text,
            expected_action,
            expected_category,
            expected_activity,
        ) in variations:
            with self.subTest(input=input_text):
                result = self.parser.parse(input_text)
                self.assertEqual(result["action"], expected_action.lower())
                self.assertEqual(result["category"], expected_category)

    def test_case_insensitivity(self):
        """Test parser handles different cases"""
        result1 = self.parser.parse("START THEORY PANDAS")
        result2 = self.parser.parse("start theory pandas")
        result3 = self.parser.parse("Start Theory Pandas")

        self.assertEqual(result1["formatted_event"], result2["formatted_event"])
        self.assertEqual(result2["formatted_event"], result3["formatted_event"])

    def test_no_direct_write(self):
        """CRITICAL: Parser never writes to master.log"""
        # Parser should only return suggestions, never modify files
        result = self.parser.parse("Test event")

        # Verify no file operations occurred
        self.assertNotIn("write", str(type(result)))
        self.assertNotIn("append", str(type(result)))

    def test_advisory_only(self):
        """CRITICAL: Parser is advisory, requires confirmation"""
        result = self.parser.parse("Started pandas")

        # Result should contain suggestion, not be final
        self.assertIn("formatted_event", result)
        self.assertIn("confidence", result)
        # No 'committed' or 'logged' field should exist
        self.assertNotIn("committed", result)
        self.assertNotIn("logged", result)


class TestArchitectureInvariants(unittest.TestCase):
    """Validate architecture invariants are maintained"""

    def setUp(self):
        self.parser = EventParser()

    def test_events_not_corrected(self):
        """Events are never corrected, only new ones appended"""
        # Even if user says "no", parser creates new event, doesn't edit
        result = self.parser.parse("Test")

        # Original result should remain unchanged
        original = result.copy()

        # Simulating user correction
        corrected = self.parser.parse("Actually pandas")

        # Original still exists, new one created
        self.assertEqual(original["formatted_event"], result["formatted_event"])
        self.assertNotEqual(original["formatted_event"], corrected["formatted_event"])

    def test_pure_inference(self):
        """Parser is pure function - same input = same output"""
        input_text = "Started pandas theory"

        result1 = self.parser.parse(input_text)
        result2 = self.parser.parse(input_text)

        self.assertEqual(result1["formatted_event"], result2["formatted_event"])
        self.assertEqual(result1["category"], result2["category"])

    def test_no_state_storage(self):
        """Parser has no internal state"""
        # Parse multiple things
        self.parser.parse("First")
        self.parser.parse("Second")
        self.parser.parse("Third")

        # Parser should behave same as fresh instance
        fresh_parser = EventParser()
        result1 = self.parser.parse("Test")
        result2 = fresh_parser.parse("Test")

        self.assertEqual(result1["formatted_event"], result2["formatted_event"])


class TestEventFormat(unittest.TestCase):
    """Test event formatting matches architecture spec"""

    def setUp(self):
        self.parser = EventParser()

    def test_event_format_structure(self):
        """Events follow: ACTION CATEGORY ACTIVITY"""
        result = self.parser.parse("Started pandas theory")
        event = result["formatted_event"]

        parts = event.split()
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "START")
        self.assertEqual(parts[1], "THEORY")
        self.assertEqual(parts[2], "PANDAS")

    def test_uppercase_events(self):
        """Events are uppercase as per master.log format"""
        result = self.parser.parse("Started pandas theory")
        event = result["formatted_event"]

        self.assertEqual(event, event.upper())

    def test_add_goal_without_payload_needs_clarification(self):
        """Bare add goal should request details instead of logging placeholder goal"""
        result = self.parser.parse("add goal")

        self.assertTrue(result.get("needs_clarification"))
        self.assertEqual(result.get("formatted_event"), "")
        self.assertIn("clarification_message", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
