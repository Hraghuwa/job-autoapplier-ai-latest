"""contextfill_page reuses ContextFill's content.js/llm.js in-page (no extension).

If ContextFill changes the scan line we patch, the scan silently widens to the
whole page (LinkedIn's search box etc.) — this test catches that.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "agents"))
import contextfill_bridge  # noqa: E402
import contextfill_page  # noqa: E402


@pytest.mark.skipif(not contextfill_bridge.extension_dir({}), reason="ContextFill checkout not present")
def test_scan_is_scoped_and_prompt_extracted():
    js, system = contextfill_page._sources({})
    assert "(window.__cfRoot || document).querySelectorAll(selector)" in js
    assert "untrusted data" in system


def test_only_empty_non_file_fields_are_sent():
    assert contextfill_page._needs_value({"type": "text", "current": ""})
    assert contextfill_page._needs_value({"type": "select", "current": "Select an option"})
    assert not contextfill_page._needs_value({"type": "text", "current": "Harsh"})
    assert not contextfill_page._needs_value({"type": "file", "current": ""})
