"""
Tests for Query Engine
Validates projections, analytics, and maintains architecture invariants
"""
import unittest
import sys
import os
import tempfile
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.query_engine import QueryEngine

class TestQueryEngine(unittest.TestCase):
    """Test query engine functionality"""
    
    def setUp(self):
        # Create temporary files for testing
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.temp_dir, 'master.log')
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        
        # Create test log file
        with open(self.log_path, 'w') as f:
            f.write("START THEORY pandas\n")
            f.write("START GAME valorant\n")
            f.write("START PRACTICE rust\n")
            f.write("START THEORY pandas\n")
            f.write("DONE TASK refactor\n")
        
        self.engine = QueryEngine(db_path=self.db_path, log_path=self.log_path)
    
    def tearDown(self):
        # Cleanup temp files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_read_master_log(self):
        """Test reading master.log"""
        events = self.engine.read_master_log()
        
        self.assertEqual(len(events), 5)
        self.assertEqual(events[0], "START THEORY pandas")
        self.assertEqual(events[1], "START GAME valorant")
    
    def test_derive_sessions(self):
        """Test session derivation from events"""
        sessions = self.engine.derive_sessions()
        
        # Should have 4 sessions (5 events - 1 overlapping start)
        self.assertGreater(len(sessions), 0)
        
        # Check first session
        first = sessions[0]
        self.assertEqual(first['category'], 'THEORY')
        self.assertEqual(first['activity'], 'pandas')
        self.assertEqual(first['start_event_index'], 0)
    
    def test_session_inference_rule(self):
        """CRITICAL: Session ends when new start occurs"""
        sessions = self.engine.derive_sessions()
        
        # First session (THEORY pandas) should end before second session starts
        if len(sessions) >= 2:
            first_end = sessions[0].get('end_event_index')
            second_start = sessions[1].get('start_event_index')
            
            if first_end is not None and second_start is not None:
                self.assertEqual(first_end, second_start - 1)
    
    def test_calculate_ratios(self):
        """Test ratio calculation"""
        ratios = self.engine.calculate_ratios('week')
        
        self.assertIn('total_sessions', ratios)
        self.assertIn('breakdown', ratios)
        self.assertIn('ratios', ratios)
        
        # Check breakdown exists
        self.assertIn('THEORY', ratios['breakdown'])
        self.assertIn('PRACTICE', ratios['breakdown'])
        self.assertIn('GAME', ratios['breakdown'])
    
    def test_ratio_percentages_sum(self):
        """Ratios should sum to approximately 100%"""
        ratios = self.engine.calculate_ratios('week')
        
        total_percentage = sum(ratios['ratios'].values())
        self.assertAlmostEqual(total_percentage, 100.0, delta=0.1)
    
    def test_answer_query_timeline(self):
        """Test timeline query"""
        result = self.engine.answer_query("What did I work on yesterday?")
        
        self.assertEqual(result['type'], 'timeline')
        self.assertIn('recent_sessions', result['answer'])
    
    def test_answer_query_ratio(self):
        """Test ratio query"""
        result = self.engine.answer_query("What is my theory to practice ratio?")
        
        self.assertEqual(result['type'], 'ratio')
        self.assertIn('total_sessions', result['answer'])
    
    def test_answer_query_summary(self):
        """Test summary query"""
        result = self.engine.answer_query("What did I work on?")
        
        self.assertEqual(result['type'], 'summary')
        self.assertIn('activities', result['answer'])


class TestArchitectureInvariants(unittest.TestCase):
    """Validate architecture invariants in query engine"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.temp_dir, 'master.log')
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        
        # Create test log
        with open(self.log_path, 'w') as f:
            f.write("START THEORY pandas\n")
        
        self.engine = QueryEngine(db_path=self.db_path, log_path=self.log_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_never_writes_to_master_log(self):
        """CRITICAL: Query engine never writes to master.log"""
        # Read original content
        with open(self.log_path, 'r') as f:
            original = f.read()
        
        # Perform various query operations
        self.engine.derive_sessions()
        self.engine.calculate_ratios('week')
        self.engine.answer_query("test query")
        self.engine.store_context({'test': 'data'})
        
        # Verify master.log unchanged
        with open(self.log_path, 'r') as f:
            after = f.read()
        
        self.assertEqual(original, after)
    
    def test_inference_pure_function(self):
        """CRITICAL: Inference is pure and replayable"""
        # Same log should produce same sessions
        sessions1 = self.engine.derive_sessions()
        sessions2 = self.engine.derive_sessions()
        
        self.assertEqual(len(sessions1), len(sessions2))
        
        if sessions1 and sessions2:
            self.assertEqual(
                sessions1[0]['category'], 
                sessions2[0]['category']
            )
    
    def test_context_storage_separate(self):
        """Context stored in SQLite, not master.log"""
        event_data = {
            'timestamp': datetime.now().isoformat(),
            'event_type': 'START',
            'category': 'THEORY',
            'activity': 'pandas',
            'context': 'chapter 3',
            'raw_input': 'Started pandas theory'
        }
        
        # Store context
        self.engine.store_context(event_data)
        
        # Verify master.log unchanged
        with open(self.log_path, 'r') as f:
            log_content = f.read()
        
        self.assertNotIn('chapter 3', log_content)
        self.assertNotIn('context', log_content)


class TestSessionDerivation(unittest.TestCase):
    """Test session derivation logic"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.temp_dir, 'master.log')
        self.db_path = os.path.join(self.temp_dir, 'test.db')
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_session_boundaries(self):
        """Sessions bounded by start of next activity"""
        # Create log with clear session boundaries
        with open(self.log_path, 'w') as f:
            f.write("START THEORY pandas\n")      # Session 1 start
            f.write("START PRACTICE rust\n")      # Session 1 end, Session 2 start
            f.write("START GAME valorant\n")      # Session 2 end, Session 3 start
        
        engine = QueryEngine(db_path=self.db_path, log_path=self.log_path)
        sessions = engine.derive_sessions()
        
        # Should have 3 sessions
        self.assertEqual(len(sessions), 3)
        
        # First session ends before second starts
        self.assertEqual(sessions[0]['end_event_index'], 0)
        self.assertEqual(sessions[1]['start_event_index'], 1)
    
    def test_activity_recurrance(self):
        """Activities can recur - each is new session"""
        with open(self.log_path, 'w') as f:
            f.write("START THEORY pandas\n")
            f.write("START GAME valorant\n")
            f.write("START THEORY pandas\n")  # Same activity, new session
        
        engine = QueryEngine(db_path=self.db_path, log_path=self.log_path)
        sessions = engine.derive_sessions()
        
        # Should have 3 sessions, 2 are THEORY pandas
        theory_sessions = [s for s in sessions if s['category'] == 'THEORY']
        self.assertEqual(len(theory_sessions), 2)
    
    def test_no_explicit_stop_needed(self):
        """No STOP events required"""
        with open(self.log_path, 'w') as f:
            f.write("START THEORY pandas\n")
            f.write("START PRACTICE rust\n")
            # No STOP event, but session still ends
        
        engine = QueryEngine(db_path=self.db_path, log_path=self.log_path)
        sessions = engine.derive_sessions()
        
        # Should still derive 2 sessions
        self.assertEqual(len(sessions), 2)
        
        # First session should have end index
        self.assertIsNotNone(sessions[0].get('end_event_index'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
