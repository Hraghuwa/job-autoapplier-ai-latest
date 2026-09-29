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


# ── Plan-level daily cap across platforms (mid-phase quota gap fix) ──────────
def test_total_across_platforms_counts_all():
    clock = FakeClock(datetime(2026, 1, 1, 9, 0))
    rl = RateLimiter(now=clock)
    rl.register_apply("u1", "linkedin")
    rl.register_apply("u1", "internshala")
    rl.register_apply("u1", "linkedin")
    assert rl.applies_in_window_total("u1") == 3
    assert rl.applies_in_window_total("other") == 0


def test_total_cap_blocks_even_when_platform_under_its_cap():
    clock = FakeClock(datetime(2026, 1, 1, 9, 0))
    rl = RateLimiter(now=clock)
    # 2 applies total, plan cap of 2 → next apply blocked though linkedin's own
    # cap (50) is nowhere near.
    rl.register_apply("u1", "linkedin")
    rl.register_apply("u1", "internshala")
    ok, reason = rl.can_apply("u1", "linkedin", total_cap=2)
    assert not ok and ("plan" in reason.lower() or "limit" in reason.lower())


def test_total_cap_none_means_no_plan_limit():
    clock = FakeClock(datetime(2026, 1, 1, 9, 0))
    rl = RateLimiter(now=clock)
    for _ in range(40):
        rl.register_apply("u1", "linkedin")
    assert rl.can_apply("u1", "linkedin", total_cap=None)[0]  # only per-platform cap applies


def test_lazy_limiter_supports_total_cap():
    from backend.services.rate_limits import _LazyLimiter
    L = _LazyLimiter()  # no redis locally → in-memory backend
    L.register_apply("uX", "linkedin")
    L.register_apply("uX", "wellfound")
    ok, _ = L.can_apply("uX", "linkedin", total_cap=2)
    assert not ok
