"""Tests for backend.services.linkedin_cookies.

Real cookie exports from Cookie-Editor / EditThisCookie include fields
Selenium's add_cookie rejects (`sameSite=None`, `hostOnly`, `session`,
`storeId`, `id`). The parser sanitises those and surfaces a clear error
when the all-important `li_at` cookie is missing — without `li_at` no
cookie-login can ever work.
"""
from __future__ import annotations

import json
import pytest

from backend.services import linkedin_cookies as lc


COOKIE_EDITOR_EXPORT = json.dumps([
    # Real Cookie-Editor shape (lots of garbage fields Selenium hates)
    {"domain": ".linkedin.com", "expirationDate": 4860000000.0,
     "hostOnly": False, "httpOnly": True, "name": "li_at",
     "path": "/", "sameSite": "no_restriction", "secure": True,
     "session": False, "storeId": "0", "value": "AQED..."},
    {"domain": ".linkedin.com", "expirationDate": 4860000000.0,
     "hostOnly": False, "httpOnly": False, "name": "JSESSIONID",
     "path": "/", "sameSite": "no_restriction", "secure": True,
     "session": False, "storeId": "0", "value": "\"ajax:1234\""},
    {"domain": ".www.linkedin.com", "hostOnly": False, "httpOnly": False,
     "name": "lang", "path": "/", "sameSite": "lax", "secure": False,
     "session": True, "storeId": "0", "value": "v=2&lang=en-us"},
])


# ── RED 1: parse_export returns Selenium-ready cookies ───────────────────────
def test_parse_export_returns_selenium_ready_cookies():
    out = lc.parse_export(COOKIE_EDITOR_EXPORT)
    assert isinstance(out, list)
    assert len(out) == 3
    for c in out:
        # add_cookie required keys
        assert "name" in c and "value" in c
        # Toxic keys must be stripped
        assert "hostOnly" not in c
        assert "session" not in c
        assert "storeId" not in c
        assert "expirationDate" not in c        # the property is named `expiry`, integer
        # sameSite normalised to one of "Strict"|"Lax"|"None" or absent
        if "sameSite" in c:
            assert c["sameSite"] in ("Strict", "Lax", "None")


# ── RED 2: extract_li_at returns the auth cookie value ──────────────────────
def test_extract_li_at_returns_value():
    out = lc.parse_export(COOKIE_EDITOR_EXPORT)
    assert lc.extract_li_at(out) == "AQED..."


# ── RED 3: missing li_at → has_valid_session is False ───────────────────────
def test_missing_li_at_flagged():
    j = json.dumps([
        {"name": "JSESSIONID", "value": "x", "domain": ".linkedin.com"}
    ])
    out = lc.parse_export(j)
    assert lc.extract_li_at(out) is None
    assert lc.has_valid_session(out) is False


# ── RED 4: valid session iff li_at exists and is non-empty ──────────────────
def test_has_valid_session_true_when_li_at_present():
    out = lc.parse_export(COOKIE_EDITOR_EXPORT)
    assert lc.has_valid_session(out) is True


# ── RED 5: invalid JSON → empty list, no exception ──────────────────────────
def test_invalid_json_returns_empty_list():
    assert lc.parse_export("not json") == []
    assert lc.parse_export("") == []
    assert lc.parse_export("{}") == []
    assert lc.parse_export("[]") == []


# ── RED 6: expiry field is converted from float epoch to int ────────────────
def test_expiry_is_int_when_present():
    out = lc.parse_export(COOKIE_EDITOR_EXPORT)
    li_at = next(c for c in out if c["name"] == "li_at")
    assert "expiry" in li_at
    assert isinstance(li_at["expiry"], int)


# ── RED 7: dump_browser_cookies converts a selenium driver's list back to JSON ─
def test_dump_browser_cookies_roundtrip():
    # Simulate the driver.get_cookies() response shape
    class _FakeDriver:
        def get_cookies(self):
            return [
                {"name": "li_at", "value": "AQED-fresh", "domain": ".linkedin.com",
                 "path": "/", "expiry": 4860000000, "secure": True, "httpOnly": True},
                {"name": "lang",  "value": "en", "domain": ".www.linkedin.com",
                 "path": "/", "secure": False, "httpOnly": False},
            ]
    drv = _FakeDriver()
    payload = lc.dump_browser_cookies(drv)
    parsed = json.loads(payload)
    assert isinstance(parsed, list) and len(parsed) == 2
    assert any(c["name"] == "li_at" and c["value"] == "AQED-fresh" for c in parsed)
