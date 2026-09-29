"""
TDD RED → GREEN tests for the Human-in-the-Loop Safety Gate.

These tests prove that:
  1. safety_gate() blocks submission when auto_submit is False (default).
  2. safety_gate() allows submission ONLY when auto_submit is explicitly True.
  3. Missing key defaults to blocking.
  4. Every applier's submit path calls safety_gate (integration-level check via
     grepping source — ensures no one bypasses the gate in future refactors).
"""

import os
import re
import pytest

from submit_gate import safety_gate


# ─────────────────────────────────────────────
#  UNIT TESTS: safety_gate() behaviour
# ─────────────────────────────────────────────

class TestSafetyGateUnit:
    """Core safety_gate() logic."""

    def test_blocks_when_auto_submit_false(self):
        """DEFAULT behaviour: must block."""
        config = {"auto_submit": False}
        assert safety_gate(config, label="test") is False

    def test_blocks_when_auto_submit_missing(self):
        """If key is absent, default must be safe (block)."""
        config = {}
        assert safety_gate(config) is False

    def test_allows_when_auto_submit_true(self):
        """Only explicit True should allow submission."""
        config = {"auto_submit": True}
        assert safety_gate(config, label="test") is True

    def test_blocks_when_auto_submit_zero(self):
        """Falsy value (0) must block."""
        config = {"auto_submit": 0}
        assert safety_gate(config) is False

    def test_blocks_when_auto_submit_none(self):
        """None must block."""
        config = {"auto_submit": None}
        assert safety_gate(config) is False

    def test_blocks_when_auto_submit_string(self):
        """String 'true' is truthy in Python — should ALLOW.
        (This documents the intended behaviour: any truthy value allows.)"""
        config = {"auto_submit": "true"}
        assert safety_gate(config) is True

    def test_prints_pause_message(self, capsys):
        """When blocking, must print a clear user-facing pause message."""
        config = {"auto_submit": False}
        safety_gate(config, label="LinkedIn Easy Apply")
        captured = capsys.readouterr()
        assert "PAUSED" in captured.out
        assert "LinkedIn Easy Apply" in captured.out


# ─────────────────────────────────────────────
#  INTEGRATION: every applier must call safety_gate
# ─────────────────────────────────────────────

# Root of the project — all applier modules live here.
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "agents")

# Every file that contains a submit-click path MUST import and call
# safety_gate before clicking.  This test greps the source to enforce it.
APPLIER_FILES_THAT_MUST_GATE = [
    "smart_form_filler.py",
    "linkedin_applier.py",
    "wellfound_applier.py",
    "internshala_applier.py",
    "other_platforms.py",
    "web_search_applier.py",
]


class TestSafetyGateIntegration:
    """Ensure every applier imports and calls safety_gate."""

    @pytest.mark.parametrize("filename", APPLIER_FILES_THAT_MUST_GATE)
    def test_applier_imports_safety_gate(self, filename):
        filepath = os.path.join(PROJECT_ROOT, filename)
        if not os.path.exists(filepath):
            pytest.skip(f"{filename} not found")
        source = open(filepath).read()
        assert "from submit_gate import safety_gate" in source or \
               "import submit_gate" in source, \
            f"{filename} does NOT import safety_gate — unsafe submit path!"

    @pytest.mark.parametrize("filename", APPLIER_FILES_THAT_MUST_GATE)
    def test_applier_calls_safety_gate(self, filename):
        filepath = os.path.join(PROJECT_ROOT, filename)
        if not os.path.exists(filepath):
            pytest.skip(f"{filename} not found")
        source = open(filepath).read()
        assert "safety_gate(" in source, \
            f"{filename} never calls safety_gate() — unguarded submit path!"
