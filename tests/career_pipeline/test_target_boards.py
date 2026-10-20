"""The web mission pulls the user's saved Portal Scan boards first."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))
import job_finder  # noqa: E402


def test_web_mission_pulls_saved_boards_first(monkeypatch):
    seen = []
    monkeypatch.setattr(job_finder, "_board_postings",
                        lambda kind, slug: seen.append((kind, slug)) or [{"url": f"https://x/{slug}"}])
    monkeypatch.setattr(job_finder, "_BOARD_GREENHOUSE_SLUGS", ["groww"])
    monkeypatch.setattr(job_finder, "_BOARD_LEVER_SLUGS", ["cred"])
    out = job_finder.fetch_board_jobs([{"kind": "lever", "slug": "acme"}, {"kind": "ashby", "slug": "nope"},
                                       {"kind": "greenhouse", "slug": "groww"}])
    assert seen[0] == ("lever", "acme")                  # user's target comes first
    assert ("ashby", "nope") not in seen                  # unsupported kinds ignored
    assert seen.count(("greenhouse", "groww")) == 1       # no duplicate fetch
    assert len(out) == 3
