"""Pure tests for smart_form_filler._kw_in_label — the field-matching predicate.

Runs in CI without a browser (the live DOM tests in tests/browser/ skip when
Chrome is absent). Locks the word-boundary fix: keyword 'lname' must NOT match
'fullname', while real phrase/word matches still work.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))

from smart_form_filler import _kw_in_label


def test_lname_does_not_match_fullname():
    # The exact bug: 'lname' ⊂ 'fullname' → wrong (last name in full-name field).
    assert _kw_in_label("lname", "full name full name fullname") is False


def test_fname_does_not_match_fullname():
    assert _kw_in_label("fname", "full name fullname") is False


def test_full_name_phrase_matches():
    assert _kw_in_label("full name", "full name full name fullname") is True


def test_single_word_matches_whole_token():
    assert _kw_in_label("name", "full name fullname") is True
    assert _kw_in_label("email", "email address email") is True


def test_underscore_keyword_matches_spaced_label():
    assert _kw_in_label("first_name", "first name") is True
    assert _kw_in_label("last_name", "your last name") is True


def test_no_match_when_absent():
    assert _kw_in_label("phone", "email address") is False


def test_empty_inputs_are_false():
    assert _kw_in_label("", "anything") is False
    assert _kw_in_label("name", "") is False


def test_substring_word_not_matched():
    # 'cgpa' must not match inside 'cgpascore' as a token, but should match
    # 'cgpa' as its own word.
    assert _kw_in_label("cgpa", "cgpascore") is False
    assert _kw_in_label("cgpa", "your cgpa") is True
