"""Tests for backend.workers.agent_tasks.classify_agent_line (audit C2).

The classifier is the most intricate piece of the run pipeline: it turns raw
applier stdout into WS events, and the ordering of its rules matters
(login_challenge must beat the generic "❌ = error" rule). Extracting it into a
pure function lets us lock the behaviour down without a live worker.
"""
from backend.workers.agent_tasks import classify_agent_line


def _cat(line):
    res = classify_agent_line(line)
    return res["category"] if res else None


def test_blank_and_noise_return_none():
    assert classify_agent_line("") is None
    assert classify_agent_line("   ") is None
    assert classify_agent_line("just some chatter") is None


def test_applied_markers():
    assert _cat("✅ Applied to Acme") == "applied"
    assert _cat("External form filled for Foo") == "applied"


def test_skipped_markers():
    assert _cat("⏭ Skipping already-seen job") == "skipped"
    assert _cat("Already applied to this one") == "skipped"
    assert _cat("Skipping low-match role") == "skipped"


def test_login_challenge_beats_generic_error():
    # Has a ❌ AND a login/challenge marker → must be login_challenge, not error.
    res = classify_agent_line("❌ LinkedIn security challenge detected")
    assert res["category"] == "login_challenge"
    assert res["platform_hint"] == "linkedin"
    assert "security challenge" in res["event"]["action_required"]


def test_captcha_with_failure_marker_is_login_challenge():
    # Preserved behaviour: a challenge keyword only becomes login_challenge when
    # a failure marker (❌/failed/error) is also present on the line.
    res = classify_agent_line("❌ CAPTCHA on naukri — solve it manually")
    assert res["category"] == "login_challenge"
    assert res["platform_hint"] == "naukri"


def test_bare_captcha_without_failure_marker_is_login_challenge():
    # Audit N2 fix: other_platforms.py prints 🚨-prefixed CAPTCHA lines with NO
    # ❌/failed/error marker. Those must still surface as login_challenge so the
    # user gets the "solve it manually" prompt instead of silence.
    res = classify_agent_line("🚨 CAPTCHA detected on naukri")
    assert res["category"] == "login_challenge"
    assert res["platform_hint"] == "naukri"


def test_bare_security_challenge_is_login_challenge():
    res = classify_agent_line("Security challenge detected — solve it manually in the window")
    assert res["category"] == "login_challenge"


def test_plain_login_word_without_failure_is_not_challenge():
    # "login" alone (e.g. "Logging in...") must NOT spam login_challenge —
    # only explicit challenge markers or login+failure do.
    assert classify_agent_line("[LinkedIn] 🔐 Initializing login...") is None


def test_generic_error_without_login_context():
    assert _cat("❌ Error: element not found") == "error"
    assert _cat("Upload failed for resume") == "error"


def test_ping_for_progress_lines():
    assert _cat("🎯 KEYWORD: product manager intern") == "ping"
    assert _cat("LINKEDIN AGENT 1/3: Founder Office") == "ping"
    assert _cat("Phase 2 starting") == "ping"


def test_event_has_no_run_id_caller_adds_it():
    # The pure classifier must NOT bake in run_id — the caller injects it.
    res = classify_agent_line("✅ Applied to Acme")
    assert "run_id" not in res["event"]
