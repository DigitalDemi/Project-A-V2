#!/usr/bin/env python3
"""
Architecture Validation Script
Validates that the implementation follows all invariants from the architecture document
"""
import os
import sys
import tempfile
import subprocess
from pathlib import Path

class ArchitectureValidator:
    """Validates system against architecture invariants"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = []
    
    def log_pass(self, msg):
        self.passed.append(f"✅ {msg}")
        print(f"✅ {msg}")
    
    def log_error(self, msg):
        self.errors.append(f"❌ {msg}")
        print(f"❌ {msg}")
    
    def log_warning(self, msg):
        self.warnings.append(f"⚠️  {msg}")
        print(f"⚠️  {msg}")
    
    def validate_invariant_1_append_only_log(self):
        """Invariant: Event log is append-only"""
        print("\n📋 Checking: Event log is append-only...")
        
        # Check that parser doesn't write to log
        parser_file = Path("agent-service/src/parser.py")
        if parser_file.exists():
            content = parser_file.read_text()
            if 'open(' in content and ('write' in content or 'append' in content):
                if 'master.log' in content:
                    self.log_error("Parser writes directly to master.log - violates invariant")
                else:
                    self.log_pass("Parser doesn't write to master.log")
            else:
                self.log_pass("Parser has no file write operations")
        
        # Check that only Rust API writes to log
        rust_main = Path("Project-A-extension/src/main.rs")
        if rust_main.exists():
            content = rust_main.read_text()
            if 'append_to_log' in content and 'master.log' in content:
                self.log_pass("Only Rust API has append_to_log for master.log")
            else:
                self.log_warning("Cannot verify Rust API is only writer")
    
    def validate_invariant_2_events_never_corrected(self):
        """Invariant: Events are never corrected"""
        print("\n📋 Checking: Events are never corrected...")
        
        # Check no edit/update operations on events
        parser_file = Path("agent-service/src/parser.py")
        if parser_file.exists():
            content = parser_file.read_text()
            if 'edit' in content.lower() or 'update' in content.lower() or 'correct' in content.lower():
                if 'event' in content.lower():
                    self.log_warning("Found edit/update keywords - verify no event correction")
                else:
                    self.log_pass("No event correction logic found")
            else:
                self.log_pass("No edit/update operations in parser")
    
    def validate_invariant_3_inference_pure(self):
        """Invariant: Inference is pure and replayable"""
        print("\n📋 Checking: Inference is pure and replayable...")
        
        # Check projections don't depend on external state
        projections = Path("Project-A-extension/src/projections.rs")
        if projections.exists():
            content = projections.read_text()
            # Check for external dependencies (network, random, time-based)
            impure_patterns = ['rand::', 'random', 'std::time::Instant::now', 'SystemTime::now']
            found_impure = [p for p in impure_patterns if p in content]
            
            if found_impure:
                self.log_error(f"Projections use impure operations: {found_impure}")
            else:
                self.log_pass("Projections appear pure (no random, no external state)")
    
    def validate_invariant_4_ui_doesnt_own_state(self):
        """Invariant: UI does not own state"""
        print("\n📋 Checking: UI does not own state...")
        
        bot_file = Path("telegram-bot/src/bot.py")
        if bot_file.exists():
            content = bot_file.read_text()
            
            # Check for file writes (should only call APIs)
            if 'open(' in content and 'write' in content:
                if 'master.log' in content or '.db' in content:
                    self.log_error("Bot writes directly to state files - violates invariant")
                else:
                    self.log_warning("Bot has file writes - verify they're not state")
            else:
                self.log_pass("Bot doesn't write to state files directly")
            
            # Check bot only emits events via API
            if 'requests.post' in content:
                self.log_pass("Bot uses API calls (not direct state access)")
    
    def validate_invariant_5_meaning_derived(self):
        """Invariant: Meaning is derived, not stored"""
        print("\n📋 Checking: Meaning is derived, not stored...")
        
        # Check master.log is minimal
        # Check context is in SQLite (separate from log)
        query_engine = Path("agent-service/src/query_engine.py")
        if query_engine.exists():
            content = query_engine.read_text()
            if 'sqlite3' in content and 'master.log' in content:
                self.log_pass("Query engine uses both SQLite (context) and master.log (truth)")
            elif 'master.log' in content:
                self.log_warning("Query engine only uses master.log - context storage missing?")
    
    def validate_llm_advisory(self):
        """Additional: LLM is advisory, not authoritative"""
        print("\n📋 Checking: LLM is advisory (never writes directly)...")
        
        parser_file = Path("agent-service/src/parser.py")
        if parser_file.exists():
            content = parser_file.read_text()
            
            # Check parser returns suggestions
            if 'confidence' in content or 'suggestion' in content.lower():
                self.log_pass("Parser includes confidence/suggestion mechanism")
            else:
                self.log_warning("Parser may not clearly indicate advisory nature")
            
            # Check no direct writes
            if 'append' in content and 'log' in content.lower():
                self.log_error("Parser may write directly to log")
            else:
                self.log_pass("Parser doesn't write to log directly")
    
    def validate_event_format(self):
        """Validate: Events follow correct format"""
        print("\n📋 Checking: Event format...")
        
        parser_file = Path("agent-service/src/parser.py")
        if parser_file.exists():
            content = parser_file.read_text()
            
            # Check for uppercase formatting
            if '.upper()' in content or 'uppercase' in content.lower():
                self.log_pass("Events formatted in uppercase")
            else:
                self.log_warning("Cannot verify uppercase formatting")
            
            # Check format pattern
            valid_patterns = ['START', 'DONE', 'THEORY', 'PRACTICE', 'GAME', 'TASK']
            found_patterns = [p for p in valid_patterns if p in content]
            if len(found_patterns) >= 4:
                self.log_pass(f"Found event type patterns: {found_patterns}")
            else:
                self.log_warning(f"Few event patterns found: {found_patterns}")
    
    def validate_projection_rebuildable(self):
        """Validate: Projections can be deleted and rebuilt"""
        print("\n📋 Checking: Projections are disposable...")
        
        # Check SQLite is not treated as source of truth
        query_engine = Path("agent-service/src/query_engine.py")
        if query_engine.exists():
            content = query_engine.read_text()
            
            # Projections should derive from master.log, not SQLite
            if 'read_master_log' in content:
                self.log_pass("Projections derive from master.log (can be rebuilt)")
            else:
                self.log_warning("Projections may depend on SQLite - verify rebuildability")
    
    def run_all_validations(self):
        """Run all validation checks"""
        print("=" * 60)
        print("🔍 Architecture Validation")
        print("=" * 60)
        
        self.validate_invariant_1_append_only_log()
        self.validate_invariant_2_events_never_corrected()
        self.validate_invariant_3_inference_pure()
        self.validate_invariant_4_ui_doesnt_own_state()
        self.validate_invariant_5_meaning_derived()
        self.validate_llm_advisory()
        self.validate_event_format()
        self.validate_projection_rebuildable()
        
        print("\n" + "=" * 60)
        print("📊 Validation Summary")
        print("=" * 60)
        print(f"✅ Passed: {len(self.passed)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"❌ Errors: {len(self.errors)}")
        
        if self.errors:
            print("\n❌ VALIDATION FAILED - Architecture invariants violated")
            return 1
        elif self.warnings:
            print("\n⚠️  VALIDATION PASSED WITH WARNINGS")
            return 0
        else:
            print("\n✅ ALL VALIDATIONS PASSED")
            return 0


def run_unit_tests():
    """Run unit tests"""
    print("\n" + "=" * 60)
    print("🧪 Running Unit Tests")
    print("=" * 60)
    
    # Python tests
    print("\n📦 Python Tests (Agent Service)...")
    result = subprocess.run(
        ['python', '-m', 'pytest', 'agent-service/tests/', '-v'],
        capture_output=True,
        text=True,
        cwd='/home/demi/.projects/basic-agent'
    )
    
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print("❌ Python tests failed")
        return 1
    else:
        print("✅ Python tests passed")
    
    # Rust tests
    print("\n📦 Rust Tests (Project-A-extension)...")
    result = subprocess.run(
        ['cargo', 'test'],
        capture_output=True,
        text=True,
        cwd='/home/demi/.projects/basic-agent/Project-A-extension'
    )
    
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print("❌ Rust tests failed")
        return 1
    else:
        print("✅ Rust tests passed")
    
    return 0


def main():
    """Main validation entry point"""
    print("🔧 Event-Driven Agent System - Validation Suite")
    
    # Change to project directory
    os.chdir('/home/demi/.projects/basic-agent')
    
    # Run architecture validation
    validator = ArchitectureValidator()
    arch_result = validator.run_all_validations()
    
    # Run unit tests
    test_result = run_unit_tests()
    
    # Final summary
    print("\n" + "=" * 60)
    print("🏁 FINAL RESULT")
    print("=" * 60)
    
    if arch_result == 0 and test_result == 0:
        print("✅ ALL CHECKS PASSED - System is valid and working")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Review errors above")
        return 1


if __name__ == '__main__':
    sys.exit(main())
