"""Phase G — Per-platform safety rails.

In-process rate limiter. For multi-worker deployments swap the backing dict
for Redis later — the API stays the same.

Two rails:
  1. Daily cap per (user, platform), sliding 24h window. Keeps the agent
     under the threshold where LinkedIn/Wellfound flag the account.
  2. Consecutive-failure auto-pause. When 3 applies in a row fail (typically
     means we tripped a captcha or the form structure changed), the limiter
     refuses further applies on that platform until a successful apply
     resets the counter.

Usage:
    rl = RateLimiter()
    ok, reason = rl.can_apply(user_id, "linkedin")
    if not ok:
        log.info("Skip: %s", reason); continue
    if submit_application(...):
        rl.register_apply(user_id, "linkedin")
        rl.register_success(user_id, "linkedin")
    else:
        rl.register_failure(user_id, "linkedin")
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Callable, Deque, Dict, Optional, Tuple

# Conservative per-platform daily caps. Tweak via env if you understand the
# tradeoffs — LinkedIn 50 is the documented ceiling before bot detection
# kicks in for new accounts.
PLATFORM_DAILY_CAP: Dict[str, int] = {
    "linkedin":    50,
    "internshala": 100,
    "wellfound":   30,
    "naukri":      50,
    "unstop":      40,
    "web_search":  60,
    "form_fill":   30,
    "analyze":     20,   # /agents/runs/{id}/analyze — caps operator LLM spend per user/day
}

WINDOW = timedelta(hours=24)
CONSECUTIVE_FAILURE_LIMIT = 3


class RateLimiter:
    """In-memory per-user, per-platform limiter. Single-process safe."""

    def __init__(self, now: Optional[Callable[[], datetime]] = None):
        self._now: Callable[[], datetime] = now or datetime.utcnow
        # (user_id, platform) -> deque of apply timestamps in the last WINDOW
        self._applies: Dict[Tuple[str, str], Deque[datetime]] = defaultdict(deque)
        # (user_id, platform) -> consecutive failure counter
        self._failures: Dict[Tuple[str, str], int] = defaultdict(int)

    # ── Internal ────────────────────────────────────────────────────────────
    def _prune(self, key: Tuple[str, str]) -> None:
        cutoff = self._now() - WINDOW
        dq = self._applies[key]
        while dq and dq[0] < cutoff:
            dq.popleft()

    # ── Public API ──────────────────────────────────────────────────────────
    def can_apply(self, user_id, platform: str) -> Tuple[bool, str]:
        key = (str(user_id), platform)
        # 1. Consecutive-failure pause has priority — surface the right reason.
        if self._failures[key] >= CONSECUTIVE_FAILURE_LIMIT:
            return False, (f"{CONSECUTIVE_FAILURE_LIMIT} consecutive failures on "
                           f"{platform}; paused until next success.")
        # 2. Daily cap.
        self._prune(key)
        cap = PLATFORM_DAILY_CAP.get(platform, 50)
        used = len(self._applies[key])
        if used >= cap:
            return False, f"daily cap reached for {platform} ({used}/{cap})"
        return True, "ok"

    def register_apply(self, user_id, platform: str) -> None:
        key = (str(user_id), platform)
        self._applies[key].append(self._now())

    def register_failure(self, user_id, platform: str) -> None:
        key = (str(user_id), platform)
        self._failures[key] += 1

    def register_success(self, user_id, platform: str) -> None:
        key = (str(user_id), platform)
        self._failures[key] = 0

    def state(self, user_id, platform: str) -> Dict[str, int]:
        """For debugging / UI status panel."""
        key = (str(user_id), platform)
        self._prune(key)
        return {
            "applies_in_window":   len(self._applies[key]),
            "cap":                 PLATFORM_DAILY_CAP.get(platform, 50),
            "consecutive_failures": self._failures[key],
        }


class RedisRateLimiter:
    """Cross-process, restart-surviving limiter with the same API as RateLimiter.

    Backed by Redis so the per-platform daily cap is enforced across the web
    process, every Celery worker, and worker restarts — which the in-memory
    limiter could not do (its counters died with the process, silently letting
    the LinkedIn-50/day account-safety rail be exceeded). See audit C3.

    Storage:
      rl:apply:{user}:{platform}  — sorted set of apply timestamps (score=epoch),
                                    pruned to the 24h window, TTL refreshed.
      rl:fail:{user}:{platform}   — integer consecutive-failure counter.
    """

    def __init__(self, client, now: Optional[Callable[[], datetime]] = None):
        self._r = client
        self._now: Callable[[], datetime] = now or datetime.utcnow

    def _epoch(self) -> float:
        return self._now().timestamp()

    def _akey(self, user_id, platform: str) -> str:
        return f"rl:apply:{user_id}:{platform}"

    def _fkey(self, user_id, platform: str) -> str:
        return f"rl:fail:{user_id}:{platform}"

    def can_apply(self, user_id, platform: str) -> Tuple[bool, str]:
        fails = int(self._r.get(self._fkey(user_id, platform)) or 0)
        if fails >= CONSECUTIVE_FAILURE_LIMIT:
            return False, (f"{CONSECUTIVE_FAILURE_LIMIT} consecutive failures on "
                           f"{platform}; paused until next success.")
        akey = self._akey(user_id, platform)
        cutoff = self._epoch() - WINDOW.total_seconds()
        self._r.zremrangebyscore(akey, 0, cutoff)
        used = self._r.zcard(akey)
        cap = PLATFORM_DAILY_CAP.get(platform, 50)
        if used >= cap:
            return False, f"daily cap reached for {platform} ({used}/{cap})"
        return True, "ok"

    def register_apply(self, user_id, platform: str) -> None:
        akey = self._akey(user_id, platform)
        now = self._epoch()
        # member must be unique → use the timestamp with a tiny disambiguator
        self._r.zadd(akey, {f"{now:.6f}": now})
        self._r.expire(akey, int(WINDOW.total_seconds()) + 60)

    def register_failure(self, user_id, platform: str) -> None:
        fkey = self._fkey(user_id, platform)
        self._r.incr(fkey)
        self._r.expire(fkey, int(WINDOW.total_seconds()))

    def register_success(self, user_id, platform: str) -> None:
        self._r.delete(self._fkey(user_id, platform))

    def state(self, user_id, platform: str) -> Dict[str, int]:
        akey = self._akey(user_id, platform)
        self._r.zremrangebyscore(akey, 0, self._epoch() - WINDOW.total_seconds())
        return {
            "applies_in_window": self._r.zcard(akey),
            "cap": PLATFORM_DAILY_CAP.get(platform, 50),
            "consecutive_failures": int(self._r.get(self._fkey(user_id, platform)) or 0),
        }


class _LazyLimiter:
    """Module singleton used by the appliers.

    Resolves to a RedisRateLimiter when REDIS_URL is reachable (shared,
    persistent), else to the in-memory RateLimiter. Resolution is cached after
    the first successful probe. Every method degrades to the in-memory backend
    if a Redis call raises, so the apply pipeline never breaks on a Redis blip.
    """

    def __init__(self):
        self._memory = RateLimiter()
        self._redis: Optional[RedisRateLimiter] = None
        self._resolved = False

    def _backend(self):
        if self._redis is not None:
            return self._redis
        if self._resolved:
            return self._memory
        self._resolved = True
        try:
            import os
            import redis as _redis
            url = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
            client = _redis.from_url(url, decode_responses=True,
                                     socket_connect_timeout=0.3, socket_timeout=0.5)
            client.ping()
            self._redis = RedisRateLimiter(client)
            return self._redis
        except Exception:
            return self._memory

    def _call(self, method: str, *args):
        backend = self._backend()
        try:
            return getattr(backend, method)(*args)
        except Exception:
            # Redis died mid-flight → fall back to in-memory for this call.
            return getattr(self._memory, method)(*args)

    def can_apply(self, user_id, platform: str) -> Tuple[bool, str]:
        return self._call("can_apply", user_id, platform)

    def register_apply(self, user_id, platform: str) -> None:
        self._call("register_apply", user_id, platform)

    def register_failure(self, user_id, platform: str) -> None:
        self._call("register_failure", user_id, platform)

    def register_success(self, user_id, platform: str) -> None:
        self._call("register_success", user_id, platform)

    def state(self, user_id, platform: str) -> Dict[str, int]:
        return self._call("state", user_id, platform)


# Module-level singleton — appliers import this. Redis-backed when available,
# in-memory otherwise; see _LazyLimiter.
default_limiter = _LazyLimiter()
