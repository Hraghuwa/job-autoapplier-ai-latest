"""Tests for backend.services.cover_note — JD-aware cover / "why this role" text.

Today every motivation/cover-letter field gets the same static
config['cover_letter']. generate() produces a short note that references the
JD's keywords using ONLY facts from the profile, with a strict fail-open: any
LLM failure, empty output, or missing JD context returns the static note. Pure
function with an injected fake llm — no network.
"""
from backend.services.cover_note import generate, resolve_cover_note, MAX_LEN


_PROFILE = {
    "full_name": "Asha Rao",
    "skills": "python, fastapi, sql",
    "experience_summary": "Engineer at Acme building APIs",
}
_STATIC = "I am a motivated engineer keen to contribute."


def _llm_ok(prompt, **kw):
    return "  Excited to bring my python and fastapi experience to your backend role.  "


def _llm_empty(prompt, **kw):
    return ""


def _llm_boom(prompt, **kw):
    raise RuntimeError("provider down")


def test_generates_tailored_note():
    out = generate(_PROFILE, jd_text="We need a python/fastapi engineer.",
                   config={"cover_letter": _STATIC}, llm=_llm_ok)
    assert "python" in out.lower()
    assert out == out.strip()                  # trimmed
    assert out != _STATIC


def test_passes_profile_and_jd_into_prompt():
    seen = {}
    def spy_llm(prompt, **kw):
        seen["prompt"] = prompt
        return "ok note"
    generate(_PROFILE, jd_text="growth marketing role", config={}, llm=spy_llm)
    assert "growth marketing" in seen["prompt"].lower()
    assert "python" in seen["prompt"].lower()  # profile facts available to model


def test_empty_llm_falls_back_to_static():
    out = generate(_PROFILE, jd_text="x", config={"cover_letter": _STATIC}, llm=_llm_empty)
    assert out == _STATIC


def test_llm_error_falls_back_to_static():
    out = generate(_PROFILE, jd_text="x", config={"cover_letter": _STATIC}, llm=_llm_boom)
    assert out == _STATIC


def test_no_jd_text_returns_static_without_calling_llm():
    called = {"n": 0}
    def counting_llm(prompt, **kw):
        called["n"] += 1
        return "should not be used"
    out = generate(_PROFILE, jd_text="", config={"cover_letter": _STATIC}, llm=counting_llm)
    assert out == _STATIC
    assert called["n"] == 0


def test_output_is_length_capped():
    long_llm = lambda prompt, **kw: "word " * 1000
    out = generate(_PROFILE, jd_text="role", config={}, llm=long_llm)
    assert len(out) <= MAX_LEN


def test_fallback_when_no_static_uses_profile_cover_letter():
    prof = dict(_PROFILE, cover_letter="profile-level note")
    out = generate(prof, jd_text="x", config={}, llm=_llm_empty)
    assert out == "profile-level note"


def test_never_raises_on_garbage_profile():
    out = generate(None, jd_text="x", config={"cover_letter": _STATIC}, llm=_llm_boom)
    assert out == _STATIC


# ── resolve_cover_note (applier accessor) ────────────────────────────────────

def test_resolve_prefers_tailored_then_static():
    assert resolve_cover_note({"_tailored_cover_note": "T", "cover_letter": "S"}) == "T"
    assert resolve_cover_note({"cover_letter": "S"}) == "S"
    assert resolve_cover_note({}) == ""


def test_resolve_ignores_blank_tailored():
    assert resolve_cover_note({"_tailored_cover_note": "  ", "cover_letter": "S"}) == "S"
