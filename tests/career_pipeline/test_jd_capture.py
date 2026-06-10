"""Tests for the JD-capture helper in agents/smart_form_filler.

Audit M7 follow-up: the resolver plumbing landed, but nothing populated
config['_current_jd'], so tailored PDFs never triggered on internshala /
web-search / form-fill. _capture_jd_text closes that: explicit _current_jd
wins; otherwise the current page's body text is the JD context; any driver
failure → None (resolver then falls back to the static PDF).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))

from smart_form_filler import _capture_jd_text  # noqa: E402


class FakeElement:
    def __init__(self, text):
        self.text = text


class FakeDriver:
    def __init__(self, body_text="We need a Python engineer with FastAPI."):
        self._body = body_text
    def find_element(self, by, value):
        return FakeElement(self._body)


class ExplodingDriver:
    def find_element(self, by, value):
        raise RuntimeError("browser crashed")


def test_explicit_current_jd_wins():
    cfg = {"_current_jd": "explicit jd text"}
    assert _capture_jd_text(FakeDriver("page text"), cfg) == "explicit jd text"


def test_falls_back_to_page_body_text():
    jd = ("We are hiring a Python engineer with FastAPI and SQLAlchemy experience "
          "to build our multi-agent automation platform. 2+ years preferred.")
    assert len(jd) >= 80  # must clear the no-JD-signal threshold
    out = _capture_jd_text(FakeDriver(jd), {})
    assert out == jd


def test_truncates_long_pages_to_8k():
    out = _capture_jd_text(FakeDriver("x" * 20000), {})
    assert len(out) == 8000


def test_short_or_empty_body_returns_none():
    # A near-empty page has no JD signal — returning None keeps the static PDF.
    assert _capture_jd_text(FakeDriver(""), {}) is None
    assert _capture_jd_text(FakeDriver("Apply now"), {}) is None


def test_driver_failure_returns_none():
    assert _capture_jd_text(ExplodingDriver(), {}) is None
