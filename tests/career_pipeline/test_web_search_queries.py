"""Tests for web_search_applier query orchestration.

The reported bugs: the run fixates on ONE job role (later keywords never get
searched before the query budget runs out) and opens too many tabs. The fix is
keyword-fair round-robin interleaving + a per-keyword query cap.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))
import web_search_applier as ws


def _cfg(keywords, **web):
    return {"role_agents": [{"name": "User Targets", "keywords": keywords}],
            "locations": ["Bangalore"], "web_search": web}


def test_every_keyword_appears_before_any_repeats():
    # Round-robin: each of the 3 keywords must get its FIRST query before any
    # keyword gets a second one. Previously keyword[0] hogged the whole budget.
    kws = ["product manager", "data analyst", "ux designer"]
    inter = ws._interleave_role_queries(_cfg(kws))
    first_three_labels = [label for label, _ in inter[:3]]
    assert set(first_three_labels) == set(kws), f"not fair: {first_three_labels}"


def test_all_keywords_represented_within_budget():
    kws = ["a role", "b role", "c role", "d role", "e role", "f role"]
    inter = ws._interleave_role_queries(_cfg(kws))
    labels_in_budget = {label for label, _ in inter[:30]}
    assert labels_in_budget == set(kws), "some roles never searched within budget"


def test_per_keyword_cap_limits_explosion():
    kws = ["only role"]
    inter = ws._interleave_role_queries(_cfg(kws, max_queries_per_keyword=4))
    assert len([1 for label, _ in inter if label == "only role"]) <= 4


def test_queries_are_deduped():
    inter = ws._interleave_role_queries(_cfg(["same", "same"]))
    qs = [q for _, q in inter]
    assert len(qs) == len(set(qs))


def test_no_keywords_returns_empty():
    assert ws._interleave_role_queries({"role_agents": [], "keywords": []}) == []
