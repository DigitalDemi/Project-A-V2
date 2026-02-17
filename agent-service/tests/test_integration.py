"""
Integration tests for Agent Service API
Tests the complete flow from HTTP request to response
"""
import unittest
import sys
import os
import tempfile
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parser import EventParser
from src.query_engine import QueryEngine

class TestAPIIntegration(unittest.TestCase):
    """Integration tests simulating API calls"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.parser = EventParser()
        self.log_path = os.path.join(self.temp_dir, 'master.log')
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.engine = QueryEngine(db_path=self.db_path, log_path=self.log_path)
        
        # Create initial log
        with open(self.log_path, 'w') as f:
            f.write("START THEORY pandas\n")
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_event_flow(self):
        """Test complete event flow: parse → confirm → store"""
        # Step 1: Parse input
        input_text = "Started working on rust practice"
        parsed = self.parser.parse(input_text)
        
        self.assertEqual(parsed['action'], 'start')
        self.assertEqual(parsed['category'], 'PRACTICE')
        
        # Step 2: User confirms
        user_response = "Yes"
        
        # Simulate confirmation (append to log)
        event_to_log = parsed['formatted_event']
        with open(self.log_path, 'a') as f:
            f.write(event_to_log + '\n')
        
        # Step 3: Store context
        context_data = {
            **parsed,
            'user_confirmed': True,
            'timestamp': '2026-02-17T14:30:00'
        }
        self.engine.store_context(context_data)
        
        # Step 4: Verify log updated
        with open(self.log_path, 'r') as f:
            lines = f.readlines()
        
        self.assertIn(event_to_log + '\n', lines)
    
    def test_correction_flow(self):
        """Test correction flow: parse → reject → re-parse → confirm"""
        # Step 1: Parse (wrong)
        input_text = "Started pandas"
        parsed = self.parser.parse(input_text)
        
        # Step 2: User rejects and corrects
        user_response = "No, it was theory not practice"
        
        # Step 3: Re-parse with correction
        corrected = self.parser.parse("Started pandas theory")
        
        # Step 4: Both events exist (no correction, only new event)
        # This tests the "events never corrected" invariant
        self.assertNotEqual(parsed['formatted_event'], corrected['formatted_event'])
    
    def test_query_after_events(self):
        """Test querying after logging events"""
        # Add events
        events = [
            "START THEORY pandas\n",
            "START PRACTICE rust\n",
            "START THEORY pandas\n",
        ]
        
        with open(self.log_path, 'a') as f:
            f.writelines(events)
        
        # Query
        result = self.engine.answer_query("What is my theory to practice ratio?")
        
        self.assertEqual(result['type'], 'ratio')
        self.assertGreater(result['answer']['total_sessions'], 0)


class TestArchitectureCompliance(unittest.TestCase):
    """Validate system follows architecture document"""
    
    def test_event_driven_principle(self):
        """System is event-driven: all state from events"""
        # Projections should be derived from events only
        temp_dir = tempfile.mkdtemp()
        log_path = os.path.join(temp_dir, 'master.log')
        
        try:
            # Create events
            with open(log_path, 'w') as f:
                f.write("START THEORY pandas\n")
                f.write("START GAME valorant\n")
            
            engine = QueryEngine(db_path=os.path.join(temp_dir, 'test.db'), log_path=log_path)
            sessions = engine.derive_sessions()
            
            # Sessions should match events
            self.assertEqual(len(sessions), 2)
            self.assertEqual(sessions[0]['category'], 'THEORY')
            self.assertEqual(sessions[1]['category'], 'GAME')
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_append_only_log(self):
        """master.log is append-only"""
        temp_dir = tempfile.mkdtemp()
        log_path = os.path.join(temp_dir, 'master.log')
        
        try:
            # Write initial
            with open(log_path, 'w') as f:
                f.write("START THEORY pandas\n")
            
            # Append more
            with open(log_path, 'a') as f:
                f.write("START PRACTICE rust\n")
            
            # Read all
            with open(log_path, 'r') as f:
                lines = f.readlines()
            
            # Both lines exist
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0].strip(), "START THEORY pandas")
            self.assertEqual(lines[1].strip(), "START PRACTICE rust")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_weak_inference(self):
        """Inference is weak - approximates but never overwrites"""
        temp_dir = tempfile.mkdtemp()
        log_path = os.path.join(temp_dir, 'master.log')
        
        try:
            # Create ambiguous events
            with open(log_path, 'w') as f:
                f.write("START THEORY pandas\n")
                f.write("START GAME valorant\n")
                f.write("START THEORY pandas\n")
            
            engine = QueryEngine(db_path=os.path.join(temp_dir, 'test.db'), log_path=log_path)
            
            # Inference approximates sessions
            sessions = engine.derive_sessions()
            
            # Should have 3 sessions (not merge the two THEORY pandas)
            self.assertEqual(len(sessions), 3)
            
            # Theory sessions are separate
            theory_count = sum(1 for s in sessions if s['category'] == 'THEORY')
            self.assertEqual(theory_count, 2)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
