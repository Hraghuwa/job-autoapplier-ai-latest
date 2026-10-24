"""Wellfound's title filter follows the user's saved job titles, not a hard-coded intern/blocklist."""

import os
import sys

import pytest

# The worker runs agents/ (run_phase_subprocess.py); the repo-root copies are stale.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agents"))
sys.modules.pop("wellfound_applier", None)
sys.modules.pop("linkedin_applier", None)
from wellfound_applier import _is_title_relevant  # noqa: E402


@pytest.mark.parametrize("title,keywords,types,ok", [
    ("Software Engineer", ["Software Engineer"], ["Full-time"], True),
    ("Business Analyst - India", ["Business Analyst"], [], True),
    ("Junior Data Scientist", ["Data Scientist"], [], True),
    ("Product Manager", ["Software Engineer"], [], False),
    ("Senior Product Manager", ["Product Manager"], ["Internship"], False),
])
def test_follows_saved_titles(title, keywords, types, ok):
    got, _why = _is_title_relevant(title, keywords, {"employment_types": types})
    assert got is ok
