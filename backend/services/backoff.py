"""Adaptive jittered inter-apply delay (PLAN Phase G — polite, ban-aware pacing).

The appliers slept random.uniform(3, 8) between applies no matter what. But a
run that just hit several failures in a row (tripped captcha, changed form,
flaky network) is precisely when hammering the platform gets the account
flagged. next_delay() keeps a healthy run fast and makes a struggling one back
off: base jittered delay × an exponential factor in the consecutive-failure
count, capped.

All pure: the rng is injected (so the curve is deterministic in tests) and
polite_sleep takes the sleep fn. delay_for() is the convenience the appliers
call — it reads the per-(user,platform) consecutive-failure count from the
shared rate limiter and sleeps. Never raises.
"""
from __future__ import annotations

import random
from typing import Callable, Optional, Tuple

MAX_DELAY_SEC = 120.0       # never wait more than 2 min between applies
_FACTOR_BASE = 1.8          # each consecutive failure multiplies the wait
_MAX_TIER = 8               # cap the exponent so the factor can't overflow


def next_delay(base_range: Tuple[float, float], consecutive_failures: int = 0,
               rng: Callable[[float, float], float] = random.uniform) -> float:
    """Seconds to wait before the next apply.

    base_range: (lo, hi) jitter band for a healthy run.
    consecutive_failures: escalates the wait; 0 → base band.
    rng(lo, hi): jitter source (injectable; default random.uniform).
    """
    try:
        lo, hi = float(base_range[0]), float(base_range[1])
    except Exception:
        lo, hi = 3.0, 8.0
    lo = max(0.0, lo)
    hi = max(lo, hi)

    failures = max(0, int(consecutive_failures or 0))
    tier = min(failures, _MAX_TIER)
    factor = _FACTOR_BASE ** tier

    base = rng(lo, hi) if hi > lo else lo
    delay = base * factor
    return float(min(MAX_DELAY_SEC, max(0.0, delay)))


def polite_sleep(base_range: Tuple[float, float], consecutive_failures: int = 0,
                 rng: Callable[[float, float], float] = random.uniform,
                 sleep_fn: Callable[[float], None] = None) -> float:
    """Compute the adaptive delay, sleep for it, and return it. Never raises."""
    import time as _time
    delay = next_delay(base_range, consecutive_failures, rng)
    fn = sleep_fn or _time.sleep
    try:
        fn(delay)
    except Exception:
        pass
    return delay


def _consecutive_failures(user_id, platform: str) -> int:
    """Best-effort read of the limiter's consecutive-failure count. 0 on any
    problem (so missing infra never slows the agent)."""
    try:
        from backend.services.rate_limits import default_limiter
        return int(default_limiter.state(user_id, platform).get("consecutive_failures", 0))
    except Exception:
        return 0


def delay_for(config, platform: str,
              rng: Callable[[float, float], float] = random.uniform,
              sleep_fn: Callable[[float], None] = None) -> float:
    """Applier convenience: adaptive sleep keyed off the live failure count for
    (config['user_id'], platform). Returns the delay. Never raises."""
    config = config or {}
    base = config.get("delay_between_applies_sec") or (3.0, 8.0)
    try:
        base = (float(base[0]), float(base[1]))
    except Exception:
        base = (3.0, 8.0)
    failures = _consecutive_failures(str(config.get("user_id", "")), platform)
    return polite_sleep(base, failures, rng=rng, sleep_fn=sleep_fn)
