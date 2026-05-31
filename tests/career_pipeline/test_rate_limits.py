"""Tests for backend.services.rate_limits — Phase G.

Contract:
    rl = RateLimiter(now=callable)
    rl.can_apply(user, platform) -> (bool, reason)
    rl.register_apply(user, platform)
    rl.register_failure(user, platform)
    rl.register_success(user, platform)

Guarantees:
    1. Per-platform daily cap is enforced (24h sliding window).
    2. Consecutive-failure auto-pause: 3 fails in a row → blocked until
       a success arrives (avoids the bot blasting a captcha 50× more).
    3. Sliding window — yesterday's applies don't count today.
    4. Different platforms tracked separately.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import pytest

from backend.services.rate_limits import RateLimiter, PLATFORM_DAILY_CAP


class FakeClock:
    def __init__(self, t: datetime):
        self.t = t
    def __call__(self) -> datetime:
        return self.t
    def advance(self, **kw):
        self.t = self.t + timedelta(**kw)


# ── RED 1: under cap → allowed; at cap → blocked ────────────────────────────
def test_daily_cap_blocks_when_reached():
    clock = FakeClock(datetime(2026, 1, 1, 9, 0))
    rl = RateLimiter(now=clock)
    cap = PLATFORM_DAILY_CAP["internshala"]
    for _ in range(cap):
        ok, _ = rl.can_apply("u1", "internshala")
        assert ok
        rl.register_apply("u1", "internshala")
    ok, reason = rl.can_apply("u1", "internshala")
    assert not ok
    assert "cap" in reason.lower()


# ── RED 2: 3 consecutive failures → blocked; success resets ─────────────────
def test_three_consecutive_failures_pause_then_success_resets():
    clock = FakeClock(datetime(2026, 1, 1, 9, 0))
    rl = RateLimiter(now=clock)
    rl.register_failure("u1", "linkedin")
    rl.register_failure("u1", "linkedin")
    rl.register_failure("u1", "linkedin")
    ok, reason = rl.can_apply("u1", "linkedin")
    assert not ok
    assert "consecutive" in reason.lower() or "fail" in reason.lower()

    rl.register_success("u1", "linkedin")
    ok, _ = rl.can_apply("u1", "linkedin")
    assert ok


# ── RED 3: sliding 24h window — old applies don't count ─────────────────────
def test_sliding_24h_window():
    clock = FakeClock(datetime(2026, 1, 1, 9, 0))
    rl = RateLimiter(now=clock)
    cap = PLATFORM_DAILY_CAP["wellfound"]
    for _ in range(cap):
        rl.register_apply("u1", "wellfound")
    assert not rl.can_apply("u1", "wellfound")[0]

    clock.advance(hours=25)   # > 24h later
    ok, _ = rl.can_apply("u1", "wellfound")
    assert ok


# ── RED 4: different platforms tracked separately ──────────────────────────
def test_platforms_independent():
    clock = FakeClock(datetime(2026, 1, 1, 9, 0))
    rl = RateLimiter(now=clock)
    # Burn linkedin to its cap
    for _ in range(PLATFORM_DAILY_CAP["linkedin"]):
        rl.register_apply("u1", "linkedin")
    # Other platforms unaffected
    assert rl.can_apply("u1", "internshala")[0]
    assert rl.can_apply("u1", "wellfound")[0]
