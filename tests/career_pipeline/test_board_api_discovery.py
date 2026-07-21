"""Regression: phase-6 discovery must not depend on scraping Google.

Google serves CAPTCHA to the automated Chrome, so google_mega_search /
search_and_apply return 0 jobs and the agent opened no tabs / applied to
nothing. fetch_board_api_jobs pulls real, applyable postings from public
Greenhouse/Lever JSON APIs (browser-free) and filters them by the user's
role keywords. These tests cover the pure keyword matcher (no network) and
the graceful-degradation contract.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))
import job_finder as jf


def test_keyword_matcher_accepts_role_titles():
    kws = ["UI/UX Designer", "Product Manager"]
    assert jf._keyword_matches("Senior Product Manager", kws)
    assert jf._keyword_matches("Lead UX Designer", kws)
    assert jf._keyword_matches("Product Design Intern", kws)


def test_keyword_matcher_rejects_unrelated_titles():
    kws = ["UI/UX Designer", "Product Manager"]
    assert not jf._keyword_matches("Backend Engineer", kws)
    assert not jf._keyword_matches("Data Scientist", kws)
    assert not jf._keyword_matches("Account Executive", kws)


def test_keyword_matcher_empty_keywords_passes_through():
    # No keywords configured → don't filter everything out.
    assert jf._keyword_matches("Anything At All", [])


def test_http_json_returns_none_on_bad_host(monkeypatch):
    # Discovery must never raise on a network/SSL failure — it degrades to [].
    assert jf._http_json("https://nonexistent.invalid/x", timeout=2) is None


def test_fetch_degrades_to_list_when_apis_unreachable(monkeypatch):
    # Force every fetch to fail; fetch_board_api_jobs must return a list, not raise.
    monkeypatch.setattr(jf, "_http_json", lambda *a, **k: None)
    out = jf.fetch_board_api_jobs(["Product Manager"], applied_urls=set(), max_jobs=10)
    assert out == []


def test_fetch_filters_and_dedups(monkeypatch):
    # Simulate a Greenhouse payload; only keyword-matching, non-applied URLs survive.
    def fake(url, timeout=15):
        if "greenhouse" in url and "groww" in url:
            return {"jobs": [
                {"title": "Product Manager", "absolute_url": "https://gh/groww/1"},
                {"title": "Backend Engineer", "absolute_url": "https://gh/groww/2"},
                {"title": "UX Designer", "absolute_url": "https://gh/groww/3"},
                {"title": "Dupe PM", "absolute_url": "https://gh/groww/dupe"},
            ]}
        return None
    monkeypatch.setattr(jf, "_http_json", fake)
    out = jf.fetch_board_api_jobs(["Product Manager", "UX Designer"],
                                  applied_urls={"https://gh/groww/dupe"}, max_jobs=10)
    assert "https://gh/groww/1" in out      # PM matched
    assert "https://gh/groww/3" in out      # designer matched
    assert "https://gh/groww/2" not in out  # engineer filtered out
    assert "https://gh/groww/dupe" not in out  # already applied → skipped
