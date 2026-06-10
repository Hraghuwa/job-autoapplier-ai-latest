"""Tests for backend.services.skiplist — time-windowed apply dedup (PLAN Phase G).

Today's tracker is a flat set of applied URLs: a job is skipped FOREVER, and
`?utm=...` query noise makes the same job look like two. This adds:
  * normalize_job_key — stable key (drops tracking params, fragments, trailing
    slash, case) so the same posting dedupes regardless of URL decoration;
  * a cooldown window — skip if applied within N days (default 90), but allow
    re-apply after, so reposted roles become applyable again;
  * legacy back-compat — old timestamp-less entries are still skipped.
All pure functions over a {key: iso_ts} map + an injected `now`.
"""
from datetime import datetime, timedelta

from backend.services.skiplist import (
    normalize_job_key, is_on_cooldown, should_skip, mark_applied,
    prune_expired, active_skip_keys, DEFAULT_COOLDOWN_DAYS,
)

NOW = datetime(2026, 6, 10, 12, 0, 0)


# ── normalize_job_key ────────────────────────────────────────────────────────

def test_strips_tracking_params_and_fragment():
    a = normalize_job_key("https://Example.com/jobs/123?utm_source=li&ref=abc#apply")
    b = normalize_job_key("https://example.com/jobs/123")
    assert a == b


def test_keeps_meaningful_query_params():
    # A real job id in the query must NOT be dropped (Greenhouse/Lever style).
    a = normalize_job_key("https://boards.greenhouse.io/x?gh_jid=999&utm_medium=x")
    b = normalize_job_key("https://boards.greenhouse.io/x?gh_jid=888")
    assert a != b


def test_trailing_slash_and_case_normalized():
    assert normalize_job_key("https://X.com/Jobs/1/") == normalize_job_key("https://x.com/Jobs/1")


def test_empty_url_is_stable():
    assert normalize_job_key("") == normalize_job_key("")
    assert normalize_job_key(None) == ""


# ── cooldown logic ───────────────────────────────────────────────────────────

def test_is_on_cooldown_within_window():
    applied = (NOW - timedelta(days=10)).isoformat()
    assert is_on_cooldown(applied, NOW, 90) is True


def test_is_off_cooldown_after_window():
    applied = (NOW - timedelta(days=91)).isoformat()
    assert is_on_cooldown(applied, NOW, 90) is False


def test_bad_timestamp_treated_as_on_cooldown():
    # A legacy/garbage stamp errs toward skipping (don't risk a double-apply).
    assert is_on_cooldown("not-a-date", NOW, 90) is True


# ── should_skip ──────────────────────────────────────────────────────────────

def test_should_skip_recent_apply():
    m = {normalize_job_key("https://x.com/j/1"): (NOW - timedelta(days=5)).isoformat()}
    assert should_skip("https://x.com/j/1?utm=a", m, NOW) is True


def test_should_not_skip_expired_apply():
    m = {normalize_job_key("https://x.com/j/1"): (NOW - timedelta(days=120)).isoformat()}
    assert should_skip("https://x.com/j/1", m, NOW) is False


def test_should_skip_legacy_flat_keys():
    legacy = {normalize_job_key("https://x.com/old")}
    assert should_skip("https://x.com/old?ref=z", {}, NOW, legacy_keys=legacy) is True


def test_unseen_job_not_skipped():
    assert should_skip("https://x.com/new", {}, NOW) is False


# ── mark_applied / prune ─────────────────────────────────────────────────────

def test_mark_applied_stamps_now():
    m = mark_applied({}, "https://x.com/j/1?utm=a", NOW)
    assert m[normalize_job_key("https://x.com/j/1")] == NOW.isoformat()


def test_mark_applied_does_not_mutate_input():
    orig = {}
    mark_applied(orig, "https://x.com/j/1", NOW)
    assert orig == {}  # returns a new dict


def test_prune_expired_drops_old_keeps_recent():
    m = {
        "old": (NOW - timedelta(days=200)).isoformat(),
        "recent": (NOW - timedelta(days=3)).isoformat(),
    }
    pruned = prune_expired(m, NOW, 90)
    assert "recent" in pruned and "old" not in pruned


def test_active_skip_keys_union_of_map_and_legacy():
    m = {"a": (NOW - timedelta(days=1)).isoformat(),
         "b": (NOW - timedelta(days=200)).isoformat()}
    keys = active_skip_keys(m, NOW, cooldown_days=90, legacy_keys={"c"})
    assert "a" in keys and "c" in keys and "b" not in keys


def test_default_cooldown_is_90():
    assert DEFAULT_COOLDOWN_DAYS == 90


# ── SkipSet (set-compatible cooldown view) ───────────────────────────────────
from backend.services.skiplist import SkipSet  # noqa: E402


def test_skipset_membership_respects_cooldown():
    m = {normalize_job_key("https://x.com/j/1"): (NOW - timedelta(days=5)).isoformat()}
    s = SkipSet(m, NOW)
    assert "https://x.com/j/1?utm_source=li" in s   # normalized + on cooldown
    assert "https://x.com/j/2" not in s


def test_skipset_expired_not_member():
    m = {normalize_job_key("https://x.com/j/1"): (NOW - timedelta(days=200)).isoformat()}
    assert "https://x.com/j/1" not in SkipSet(m, NOW)


def test_skipset_add_then_member():
    s = SkipSet({}, NOW)
    assert "https://x.com/new" not in s
    s.add("https://x.com/new?utm_medium=x")
    assert "https://x.com/new" in s


def test_skipset_legacy_keys_member():
    s = SkipSet({}, NOW, legacy_keys={normalize_job_key("https://x.com/old")})
    assert "https://x.com/old?ref=1" in s


def test_skipset_applied_map_is_pruned():
    m = {"recent": (NOW - timedelta(days=1)).isoformat(),
         "old": (NOW - timedelta(days=200)).isoformat()}
    s = SkipSet(m, NOW)
    assert "recent" in s.applied_map and "old" not in s.applied_map
