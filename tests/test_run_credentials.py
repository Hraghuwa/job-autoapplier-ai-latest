"""Pure tests for agents._missing_credential — run-start credential gate.

Guards the fix: a cookie-authenticated LinkedIn user (the supported auth path)
must be allowed to run; password is not the only valid LinkedIn credential.
"""
from backend.routers.agents import _missing_credential


def test_linkedin_password_ok():
    creds = {"linkedin": {"email": "a@b.com", "password": "x"}}
    assert _missing_credential([1], creds) is None


def test_linkedin_cookies_ok_without_password():
    # The bug: this used to be blocked for lacking email/password.
    creds = {"linkedin_cookies": "[{...}]"}
    assert _missing_credential([1], creds) is None


def test_linkedin_nothing_is_missing():
    assert _missing_credential([1], {}) == (1, "linkedin")


def test_other_platform_requires_password():
    assert _missing_credential([2], {"linkedin_cookies": "x"}) == (2, "internshala")
    assert _missing_credential([2], {"internshala": {"email": "a", "password": "b"}}) is None


def test_phase_without_cred_requirement_ok():
    assert _missing_credential([6, 7], {}) is None  # web_search / form_fill need no creds


def test_first_missing_reported():
    creds = {"linkedin_cookies": "x"}  # phase 1 ok, phase 4 missing
    assert _missing_credential([1, 4], creds) == (4, "naukri")
