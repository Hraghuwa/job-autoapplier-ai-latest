"""ADR-001: postings are filtered by role, level, tech and location BEFORE a tab opens.

Cases are real titles the old 5-letter-stem matcher let through for
"Consultant / Team Lead / Product Manager" (2026-10-02 repro).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))
import job_targeting as jt

CFG = {
    "role_agents": [{"keywords": ["Business Analyst", "Associate Product Manager", "Operations Associate"]}],
    "locations": ["Bangalore", "Remote"],
    "profile": {"skills": "Retail operations, inventory, Excel, vendor management", "years_of_experience": "4"},
}


def ok(title, loc="Bengaluru, India", cfg=CFG):
    return jt.check(title, loc, jt.target_ctx(cfg))[0]


def test_role_needs_every_keyword_word_not_a_stem():
    assert ok("Business Analyst")
    assert ok("Associate Product Manager")
    assert ok("Operations Associate")
    assert not ok("Engineering Manager")          # 'manag' stem used to match
    assert not ok("Product Research Specialist")  # 'produ' stem used to match


def test_level_capped_at_associate_for_entry_target():
    assert not ok("Senior Business Analyst")
    assert not ok("Director of Product Management, Associate Product Manager Org")
    assert not ok("Business Analyst Team Lead")
    assert jt.title_level("Associate Renewals Manager") == "associate"
    assert jt.title_level("Product Manager") == "mid"
    mid = dict(CFG, role_agents=[{"keywords": ["Product Manager"]}], target_seniority="mid")
    assert ok("Product Manager", cfg=mid)
    assert not ok("Product Manager", cfg=dict(mid, target_seniority="entry"))


def test_tech_roles_skipped_for_non_tech_profile():
    cfg = dict(CFG, role_agents=[{"keywords": ["Analyst"]}])
    assert ok("Business Analyst", cfg=cfg)
    assert not ok("Data Platform Analyst", cfg=cfg)
    tech = dict(cfg, profile={"skills": "Python, SQL, AWS"})
    assert ok("Data Platform Analyst", cfg=tech)


def test_location_rejects_foreign_only_remote():
    assert ok("Business Analyst", "Remote, India")
    assert ok("Business Analyst", "Bangalore")
    assert ok("Business Analyst", "")
    assert not ok("Business Analyst", "Remote, United States")
    assert not ok("Business Analyst", "Remote Ireland; Remote, Israel")
    assert not ok("Business Analyst", "London")


def test_never_raises_on_garbage():
    assert jt.check(None, None, jt.target_ctx({}))[0] is False
    assert jt.target_ctx(None)["keywords"] == []
