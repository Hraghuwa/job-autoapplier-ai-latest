"""LinkedIn session-cookie helpers.

Browser cookie extensions (Cookie-Editor, EditThisCookie) export cookie
arrays in a format Selenium's `WebDriver.add_cookie` cannot consume — they
carry extra fields like `sameSite="no_restriction"`, `hostOnly`, `session`,
`storeId`, `id`, and `expirationDate` (float). `add_cookie` raises on any
of these. This module sanitises the export to Selenium-ready dicts and
exposes the two questions the agent actually needs to answer:

    1. Is there an `li_at` cookie? (no li_at = no auth, no session)
    2. After a successful logged-in browse, what cookies should we store
       so the next run skips login entirely?

`parse_export` never raises — invalid input returns `[]` so the LinkedIn
applier can always make a yes/no decision without try/except.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Selenium-accepted keys for add_cookie (per chromedriver source). Anything
# else is dropped silently.
_ALLOWED = {"name", "value", "path", "domain", "secure", "httpOnly", "expiry", "sameSite"}

# Cookie-Editor → Selenium sameSite normalisation.
_SAMESITE_MAP = {
    "no_restriction": "None",
    "unspecified":    None,        # → drop
    "lax":            "Lax",
    "strict":         "Strict",
    "none":           "None",
}


def parse_export(raw: str) -> List[Dict[str, Any]]:
    """Parse a Cookie-Editor / EditThisCookie JSON export → Selenium-ready
    cookie dicts. Returns [] on any error (never raises)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    out: List[Dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        value = entry.get("value")
        if not isinstance(name, str) or not name:
            continue
        if value is None:
            continue

        cookie: Dict[str, Any] = {"name": name, "value": str(value)}

        # Domain — Selenium accepts the leading dot but not on every driver
        # version; strip it for safety. We will navigate to the matching
        # site before add_cookie so the host check passes.
        dom = entry.get("domain")
        if isinstance(dom, str) and dom:
            cookie["domain"] = dom.lstrip(".")

        # Path
        path = entry.get("path")
        if isinstance(path, str) and path:
            cookie["path"] = path

        # secure / httpOnly are booleans, pass through if present
        for b in ("secure", "httpOnly"):
            if isinstance(entry.get(b), bool):
                cookie[b] = entry[b]

        # Expiry — chromedriver requires an int. Cookie-Editor calls it
        # `expirationDate` and emits a float. Skip when session cookie.
        if entry.get("session") is True:
            pass
        else:
            exp = entry.get("expirationDate") or entry.get("expiry")
            if isinstance(exp, (int, float)) and exp > 0:
                cookie["expiry"] = int(exp)

        # sameSite normalisation
        ss = entry.get("sameSite")
        if isinstance(ss, str):
            mapped = _SAMESITE_MAP.get(ss.strip().lower())
            if mapped is not None:
                cookie["sameSite"] = mapped

        # Final scrub — only keep allowed keys
        out.append({k: v for k, v in cookie.items() if k in _ALLOWED})
    return out


def extract_li_at(cookies: List[Dict[str, Any]]) -> Optional[str]:
    """Return the `li_at` cookie value, or None. This cookie carries the
    actual session token — without it nothing else matters."""
    for c in cookies or []:
        if isinstance(c, dict) and c.get("name") == "li_at":
            v = c.get("value") or ""
            return v if v else None
    return None


def has_valid_session(cookies: List[Dict[str, Any]]) -> bool:
    """Cheap pre-flight: True iff li_at exists and is non-empty.

    Doesn't prove the session is still valid (only LinkedIn can confirm
    that), but rules out the most common failure mode where the user
    exported cookies before logging in.
    """
    return bool(extract_li_at(cookies))


def dump_browser_cookies(driver) -> str:
    """After a successful logged-in session, snapshot the driver's cookies
    as a JSON string suitable for re-uploading via /onboarding/linkedin-cookies.

    Use this to refresh stored cookies whenever the agent finishes a run
    while still logged in — keeps the cached session alive across runs
    without the user re-exporting.
    """
    cookies = []
    try:
        for c in driver.get_cookies() or []:
            if not isinstance(c, dict):
                continue
            cookies.append({k: v for k, v in c.items() if k in _ALLOWED | {"expirationDate"}})
    except Exception:
        return "[]"
    return json.dumps(cookies)
