"""Tests for backend.services.apply_decision.should_apply — the orchestration
the appliers actually call: JD text → signature (jd_analyser) → fit score
(fit_scorer) → decision. Honours an opt-out and never raises (fail-open).
"""
from backend.services.apply_decision import should_apply


_GOOD_JD = ('We are hiring a Python backend engineer. Must have: python, fastapi. '
            'Nice to have: docker. This is a junior role.')

# A fake JD-analyser LLM returning strict JSON, so no network is needed.
def _fake_llm_good(prompt, **kw):
    return ('{"keywords":["python","fastapi"],"must_haves":["python","fastapi"],'
            '"nice_to_haves":["docker"],"seniority":"junior","archetype":"backend",'
            '"red_flags":[]}')

def _fake_llm_unpaid(prompt, **kw):
    return ('{"keywords":["python"],"must_haves":["python"],"nice_to_haves":[],'
            '"seniority":"intern","archetype":"backend","red_flags":["unpaid position"]}')


def _profile(skills="python, fastapi, docker, sql"):
    return {"skills": skills, "years_of_experience": 2,
            "experience": [{"role": "Engineer", "bullets": [{"id": "b1", "text": "python fastapi"}]}]}


def test_good_fit_applies():
    cfg = {"profile": _profile(), "_jd_llm": _fake_llm_good}
    d = should_apply(cfg, jd_text=_GOOD_JD, title="Python Backend Engineer")
    assert d.apply is True
    assert d.score >= 55


def test_unpaid_is_vetoed():
    cfg = {"profile": _profile(), "_jd_llm": _fake_llm_unpaid}
    d = should_apply(cfg, jd_text="Unpaid python internship, no stipend.",
                     title="Python Intern")
    assert d.apply is False
    assert d.vetoed is True


def test_no_jd_text_is_fail_open_apply():
    # Without JD context we can't score — don't block the apply (preserve today's
    # behaviour), just say so.
    d = should_apply({"profile": _profile()}, jd_text=None, title="Anything")
    assert d.apply is True
    assert any("no jd" in r.lower() or "context" in r.lower() for r in d.reasons)


def test_disabled_via_config_always_applies():
    cfg = {"profile": _profile(), "_jd_llm": _fake_llm_unpaid, "fit_gate_enabled": False}
    d = should_apply(cfg, jd_text="unpaid", title="x")
    assert d.apply is True


def test_custom_floor_from_config_match_threshold():
    # match_threshold in config should drive the floor.
    cfg = {"profile": _profile(skills="python"), "_jd_llm": _fake_llm_good,
           "match_threshold": 99}
    d = should_apply(cfg, jd_text=_GOOD_JD, title="Python Engineer")
    assert d.apply is False  # 99 floor is unreachable for partial coverage


def test_never_raises_on_bad_llm():
    def boom(prompt, **kw):
        raise RuntimeError("llm down")
    d = should_apply({"profile": _profile(), "_jd_llm": boom},
                     jd_text=_GOOD_JD, title="x")
    assert d.apply is True  # fail-open
