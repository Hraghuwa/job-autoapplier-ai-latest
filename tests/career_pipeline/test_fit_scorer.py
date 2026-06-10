"""Tests for backend.services.fit_scorer — the agents' pre-apply decision engine.

The product idea is volume x relevance WITHOUT getting the account banned. An
agent that applies to every title-search hit burns applies, LLM cost, and
ban-risk on jobs it can't win. score_fit() lets each applier spend an
application only when the candidate genuinely fits: must-have coverage,
title/keyword overlap, seniority sanity, and hard red-flag vetoes. Pure
function over a JDSignature + profile, so it's fully testable without a browser.
"""
from backend.services.career_schemas import JDSignature
from backend.services.fit_scorer import score_fit, FitDecision, DEFAULT_FLOOR


def _sig(**kw):
    base = dict(jd_hash="h", keywords=["python", "fastapi"], must_haves=["python"],
                nice_to_haves=["docker"], seniority="junior", archetype="backend",
                red_flags=[])
    base.update(kw)
    return JDSignature(**base)


def _profile(skills="python, fastapi, sql", experience=None, years=2):
    return {
        "skills": skills,
        "experience": experience or [{"role": "Engineer", "company": "Acme",
                                      "bullets": [{"id": "b1", "text": "Built python APIs with fastapi"}]}],
        "years_of_experience": years,
    }


def test_returns_fitdecision_with_score_and_reasons():
    d = score_fit(_sig(), _profile(), title="Python Engineer Intern")
    assert isinstance(d, FitDecision)
    assert 0 <= d.score <= 100
    assert isinstance(d.reasons, list) and d.reasons
    assert d.apply in (True, False)


def test_strong_match_applies_above_floor():
    d = score_fit(_sig(must_haves=["python", "fastapi"]),
                  _profile(skills="python, fastapi, sql, docker"),
                  title="Backend Python Engineer")
    assert d.score >= DEFAULT_FLOOR
    assert d.apply is True


def test_must_haves_not_covered_drops_score():
    # JD demands skills the candidate lacks → low coverage → skip.
    d = score_fit(_sig(must_haves=["rust", "kubernetes", "terraform"]),
                  _profile(skills="python, html"),
                  title="Platform Engineer")
    assert d.components["must_have_coverage"] < 0.5
    assert d.apply is False
    assert any("must-have" in r.lower() or "coverage" in r.lower() for r in d.reasons)


def test_hard_red_flag_vetoes_regardless_of_score():
    # Even a perfect skills match must be skipped if the JD is unpaid/scam.
    d = score_fit(_sig(must_haves=["python"], red_flags=["unpaid position"]),
                  _profile(skills="python, fastapi"),
                  title="Python Engineer")
    assert d.apply is False
    assert d.vetoed is True
    assert any("unpaid" in r.lower() or "red flag" in r.lower() for r in d.reasons)


def test_soft_red_flag_penalizes_but_not_veto():
    d = score_fit(_sig(red_flags=["fast-paced environment"]),
                  _profile(skills="python, fastapi"), title="Python Engineer")
    assert d.vetoed is False  # vague culture phrase is not a hard veto


def test_seniority_mismatch_penalized():
    # Senior role, junior candidate (1 yr) → penalty.
    junior = score_fit(_sig(seniority="senior"), _profile(years=1), title="Senior Engineer")
    fit = score_fit(_sig(seniority="junior"), _profile(years=1), title="Junior Engineer")
    assert junior.components["seniority_fit"] < fit.components["seniority_fit"]


def test_title_overlap_contributes():
    on = score_fit(_sig(keywords=["product", "manager"]),
                   _profile(skills="product strategy"), title="Product Manager Intern")
    off = score_fit(_sig(keywords=["product", "manager"]),
                    _profile(skills="product strategy"), title="Welder")
    assert on.components["title_match"] > off.components["title_match"]


def test_empty_signature_is_neutral_not_crash():
    d = score_fit(JDSignature(jd_hash="h"), _profile(), title="Anything")
    assert isinstance(d, FitDecision)
    # No must_haves to fail → coverage treated as full; should not hard-skip.
    assert d.components["must_have_coverage"] == 1.0


def test_custom_floor_changes_decision():
    sig = _sig(must_haves=["python", "docker"])
    prof = _profile(skills="python")  # ~half coverage → mid score
    lenient = score_fit(sig, prof, title="Python Engineer", floor=10)
    strict = score_fit(sig, prof, title="Python Engineer", floor=95)
    assert lenient.apply is True
    assert strict.apply is False


def test_never_raises_on_garbage_profile():
    d = score_fit(_sig(), {"skills": None, "experience": "not a list"}, title=None)
    assert isinstance(d, FitDecision)
