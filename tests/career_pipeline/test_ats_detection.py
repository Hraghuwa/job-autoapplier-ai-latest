"""Regression: web_search_applier.detect_ats_type must NEVER raise.

It used to call agent_vision.detect_ats_type (which doesn't exist) for any
non-obvious ATS page → AttributeError aborted apply_to_job_url for the majority
of jobs (LinkedIn, company sites) → 0 applications, agent churned.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))
import web_search_applier as ws


def test_known_ats_by_url():
    assert ws.detect_ats_type(None, "https://jobs.lever.co/foo/abc") == "lever"
    assert ws.detect_ats_type(None, "https://boards.greenhouse.io/x?gh_jid=9") == "greenhouse"
    assert ws.detect_ats_type(None, "https://acme.myworkdayjobs.com/job/1") == "workday"


def test_unknown_ats_returns_generic_without_raising():
    # The bug: this raised AttributeError (agent_vision.detect_ats_type missing).
    assert ws.detect_ats_type(None, "https://acme.com/careers/eng-123") == "generic"
    assert ws.detect_ats_type(None, "https://www.linkedin.com/jobs/view/999") == "generic"


def test_never_raises_even_if_vision_present_but_broken(monkeypatch):
    import agent_vision
    monkeypatch.setattr(agent_vision, "detect_ats_type",
                        lambda d, c: (_ for _ in ()).throw(RuntimeError("boom")), raising=False)
    assert ws.detect_ats_type(None, "https://acme.com/careers/x") == "generic"  # swallowed
