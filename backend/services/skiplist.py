"""Time-windowed apply dedup — PLAN Phase G ("never re-apply within 90 days").

The legacy tracker stores a flat set of applied URLs, so a job is skipped
forever and `?utm=...`-decorated URLs dedupe inconsistently. This module adds a
stable job key + a cooldown window, as pure functions over a {key: iso_ts} map
plus an injected `now` (no hidden clock → fully testable).

Behaviour:
  * normalize_job_key drops tracking params (utm_*, ref, fbclid, gclid, source,
    src), the fragment, trailing slash, and case — but KEEPS meaningful query
    params like gh_jid / lever ids so distinct postings stay distinct.
  * should_skip → True if the job was applied to within `cooldown_days`, or it
    is in the legacy flat set (timestamp-less → always skip, back-compat).
  * after the window a job rolls OFF the skip list, so a reposted role becomes
    applyable again — more shots over time without spamming the same posting.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, Iterable, Optional, Set
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

DEFAULT_COOLDOWN_DAYS = 90

# Query params that are pure tracking noise — dropped before hashing.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "refid", "ref_id", "fbclid", "gclid", "source", "src", "trk",
    "trackingid", "originalsubdomain", "li_fat_id",
}


def normalize_job_key(url: Optional[str]) -> str:
    """Stable hash of a job URL with tracking noise stripped. '' for falsy."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = ""  # ignore http/https difference
        netloc = parts.netloc.lower()
        path = (parts.path or "").rstrip("/").lower()
        kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
                if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm")]
        kept.sort()
        query = urlencode(kept)
        canon = urlunsplit((scheme, netloc, path, query, ""))  # no fragment
    except Exception:
        canon = url.strip().lower()
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:24]


def is_on_cooldown(applied_at_iso: str, now: datetime,
                   cooldown_days: int = DEFAULT_COOLDOWN_DAYS) -> bool:
    """True if `applied_at_iso` is within `cooldown_days` of `now`.
    An unparseable timestamp errs toward True (skip) to avoid double-applies."""
    try:
        applied = datetime.fromisoformat(applied_at_iso)
    except (TypeError, ValueError):
        return True
    return (now - applied).days < cooldown_days


def should_skip(url: Optional[str], applied_map: Dict[str, str], now: datetime,
                cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
                legacy_keys: Optional[Set[str]] = None) -> bool:
    key = normalize_job_key(url)
    if not key:
        return False
    if legacy_keys and key in legacy_keys:
        return True
    ts = (applied_map or {}).get(key)
    if ts is None:
        return False
    return is_on_cooldown(ts, now, cooldown_days)


def mark_applied(applied_map: Dict[str, str], url: Optional[str],
                 now: datetime) -> Dict[str, str]:
    """Return a NEW map with `url`'s key stamped at `now` (input untouched)."""
    out = dict(applied_map or {})
    key = normalize_job_key(url)
    if key:
        out[key] = now.isoformat()
    return out


def prune_expired(applied_map: Dict[str, str], now: datetime,
                  cooldown_days: int = DEFAULT_COOLDOWN_DAYS) -> Dict[str, str]:
    """Drop entries past the cooldown so the map can't grow unbounded."""
    return {k: ts for k, ts in (applied_map or {}).items()
            if is_on_cooldown(ts, now, cooldown_days)}


def active_skip_keys(applied_map: Dict[str, str], now: datetime,
                     cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
                     legacy_keys: Optional[Iterable[str]] = None) -> Set[str]:
    """All keys that should currently be skipped: on-cooldown map entries ∪
    legacy flat keys. Lets callers keep a simple set-membership interface."""
    active = {k for k, ts in (applied_map or {}).items()
              if is_on_cooldown(ts, now, cooldown_days)}
    if legacy_keys:
        active |= set(legacy_keys)
    return active


class SkipSet:
    """A set-compatible view that backs the appliers' existing `applied_urls`
    interface with cooldown + key normalization — no applier changes needed.

        skip = SkipSet(tracker.get("applied_at"), now, legacy_keys=...)
        if url in skip:        # True iff on cooldown / legacy
            continue
        skip.add(url)          # stamps `now`
        tracker["applied_at"] = skip.applied_map   # persist

    `in` normalizes the URL and checks the cooldown window; `add` stamps now.
    Iteration/len reflect the active (on-cooldown) keys plus legacy keys.
    """

    def __init__(self, applied_map=None, now: Optional[datetime] = None,
                 cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
                 legacy_keys: Optional[Iterable[str]] = None):
        self._map = dict(applied_map or {})
        self._now = now or datetime.utcnow()
        self._cd = cooldown_days
        self._legacy = set(legacy_keys or [])

    def __contains__(self, url) -> bool:
        return should_skip(url, self._map, self._now, self._cd, self._legacy)

    def add(self, url) -> None:
        self._map = mark_applied(self._map, url, self._now)

    def __iter__(self):
        return iter(active_skip_keys(self._map, self._now, self._cd, self._legacy))

    def __len__(self) -> int:
        return len(active_skip_keys(self._map, self._now, self._cd, self._legacy))

    @property
    def applied_map(self) -> Dict[str, str]:
        """The pruned {key: ts} map to persist back to the tracker."""
        return prune_expired(self._map, self._now, self._cd)
