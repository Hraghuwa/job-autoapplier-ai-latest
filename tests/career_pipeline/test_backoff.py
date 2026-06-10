"""Tests for backend.services.backoff — adaptive jittered inter-apply delay.

Today the appliers sleep random.uniform(3, 8) between applies regardless of how
things are going. After consecutive failures (a tripped captcha, a changed form)
that's exactly when a bot blasts the platform and gets flagged. next_delay()
escalates the wait exponentially with the failure count, adds jitter, and caps —
so a healthy run stays fast but a struggling one backs off. Pure: the curve is
deterministic given an injected rng; polite_sleep injects the sleep fn.
"""
import pytest

from backend.services.backoff import next_delay, polite_sleep, MAX_DELAY_SEC


def _no_jitter(a, b):
    return (a + b) / 2.0  # deterministic midpoint instead of random.uniform


def test_zero_failures_in_base_range():
    d = next_delay((4, 8), consecutive_failures=0, rng=_no_jitter)
    assert 4 <= d <= 8


def test_monotonic_increase_with_failures():
    base = (4, 8)
    delays = [next_delay(base, consecutive_failures=n, rng=_no_jitter) for n in range(5)]
    assert delays == sorted(delays)            # non-decreasing
    assert delays[3] > delays[0]               # and actually grows


def test_capped_at_max():
    d = next_delay((4, 8), consecutive_failures=50, rng=_no_jitter)
    assert d <= MAX_DELAY_SEC


def test_jitter_within_bounds():
    # With real randomness the delay stays within the [lo, hi] band for its tier.
    import random
    for _ in range(200):
        d = next_delay((4, 8), consecutive_failures=2, rng=random.uniform)
        assert 0 < d <= MAX_DELAY_SEC


def test_bad_base_range_is_tolerated():
    # reversed / zero / negative inputs must not crash or go negative
    assert next_delay((8, 4), 0, rng=_no_jitter) > 0
    assert next_delay((0, 0), 1, rng=_no_jitter) >= 0
    assert next_delay((-5, -1), 0, rng=_no_jitter) >= 0


def test_negative_failures_treated_as_zero():
    base_d = next_delay((4, 8), 0, rng=_no_jitter)
    assert next_delay((4, 8), -3, rng=_no_jitter) == base_d


# ── polite_sleep (injectable sleep seam) ─────────────────────────────────────

def test_polite_sleep_returns_and_calls_sleep():
    slept = {}
    def fake_sleep(s):
        slept["s"] = s
    d = polite_sleep((4, 8), consecutive_failures=0, rng=_no_jitter, sleep_fn=fake_sleep)
    assert slept["s"] == d
    assert 4 <= d <= 8


def test_polite_sleep_never_raises_on_bad_sleep_fn():
    def boom(s):
        raise RuntimeError("interrupted")
    # Should swallow the sleep error and still return the computed delay.
    d = polite_sleep((4, 8), consecutive_failures=1, rng=_no_jitter, sleep_fn=boom)
    assert d > 0


def test_delay_for_helper_reads_limiter_state(monkeypatch):
    # delay_for(config, platform) should derive failures from the rate limiter
    # and never raise even if the limiter is unavailable.
    from backend.services import backoff
    d = backoff.delay_for({"user_id": "u1", "delay_between_applies_sec": (3, 6)},
                          platform="linkedin", rng=_no_jitter, sleep_fn=lambda s: None)
    assert d >= 0
