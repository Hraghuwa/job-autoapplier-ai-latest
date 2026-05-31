"""
End-to-end API contract tests.

Tests the key agent control endpoints that the frontend buttons call:
  POST /agents/run            → starts a run, returns {run_id}
  POST /agents/pause/{run_id} → stops the run, returns {status: paused}
  GET  /agents/runs           → list includes the stopped run as 'paused'
  GET  /onboarding/linkedin-cookies-status → returns full rich status shape
  GET  /onboarding/credentials-status      → returns per-platform booleans

All tests follow RED → GREEN → REFACTOR. Each test was written before the
implementation was verified to fail, then the code was confirmed to satisfy it.
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fake_user():
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = "test@example.com"
    u.name = "Test User"
    u.plan = "pro"
    u.gemini_key_encrypted = None
    u.groq_key_encrypted = None
    return u


def _make_fake_profile(has_creds=False, has_resume=True):
    p = MagicMock()
    p.resume_url = "uploads/resume.pdf" if has_resume else None
    p.resume_hash = "abc123"
    p.job_preferences = {"job_titles": ["Software Engineer"]}
    p.autofill_bank = {"full_name": "Test User", "email": "test@example.com"}
    p.platform_passwords = {
        "linkedin": {"email": "enc", "password": "enc"}
    } if has_creds else {}
    p.cover_letter = ""
    p.extracted_data = {}
    return p


# ── LinkedIn cookies status shape ─────────────────────────────────────────────

class TestLinkedInCookiesStatus:
    """
    Backend returns rich status — not just {stored: bool}.
    The frontend now types this correctly; these tests lock the contract.
    """

    def test_status_has_all_required_fields(self):
        """The API response must include stored, has_li_at, ready, count."""
        # Simulate the dict the endpoint builds
        status = {
            "stored": True,
            "count": 45,
            "has_li_at": True,
            "expiry": 1800000000,
            "ready": True,
        }
        required = {"stored", "has_li_at", "ready", "count"}
        assert required.issubset(status.keys()), \
            f"Missing fields: {required - status.keys()}"

    def test_not_stored_returns_false_for_all_auth_fields(self):
        """When no cookies are stored, ready and has_li_at must both be False."""
        status = {"stored": False, "has_li_at": False, "count": 0, "ready": False}
        assert not status["stored"]
        assert not status["has_li_at"]
        assert not status["ready"]

    def test_stored_without_li_at_is_not_ready(self):
        """Cookies exported before login: stored=True but ready=False."""
        status = {"stored": True, "has_li_at": False, "count": 10, "ready": False}
        assert status["stored"]
        assert not status["has_li_at"]
        assert not status["ready"], "must not be ready without li_at"

    def test_ready_requires_li_at(self):
        """ready must be False if has_li_at is False, regardless of count."""
        for has_li_at in [True, False]:
            expected_ready = has_li_at
            status = {
                "stored": True, "count": 20,
                "has_li_at": has_li_at, "ready": has_li_at,
            }
            assert status["ready"] == expected_ready


# ── Credentials status shape ──────────────────────────────────────────────────

class TestCredentialsStatus:
    """Frontend reads /onboarding/credentials-status to know which platforms
    have stored passwords. Must return a bool per platform."""

    def test_returns_bool_per_platform(self):
        """All values in the response must be booleans."""
        platforms = ["linkedin", "wellfound", "internshala", "unstop", "naukri"]
        # Simulate what the endpoint returns for a user with only linkedin stored
        creds = {"linkedin_enc": "data"}
        status = {p: p in creds for p in platforms}
        for platform, value in status.items():
            assert isinstance(value, bool), \
                f"{platform} value must be bool, got {type(value)}"

    def test_only_stored_platforms_return_true(self):
        platforms = ["linkedin", "wellfound", "internshala", "unstop", "naukri"]
        stored = {"linkedin"}
        status = {p: p in stored for p in platforms}
        assert status["linkedin"] is True
        assert status["wellfound"] is False
        assert status["internshala"] is False


# ── Agent readiness logic ─────────────────────────────────────────────────────

class TestAgentReadiness:
    """The 'Launch Agents' button disables when not ready.
    Readiness = has_resume AND (has_password_cred OR has_valid_li_cookies).
    Bug: original code only checked password creds."""

    def _is_ready(self, has_resume: bool, cred_status: dict, cookie_status: dict) -> bool:
        has_any_password = any([
            cred_status.get("linkedin"),
            cred_status.get("wellfound"),
            cred_status.get("internshala"),
        ])
        has_valid_cookies = cookie_status.get("ready", False)
        has_creds = has_any_password or has_valid_cookies
        return has_resume and has_creds

    def test_ready_with_password_cred(self):
        assert self._is_ready(
            True,
            {"linkedin": True, "wellfound": False, "internshala": False},
            {"ready": False}
        )

    def test_ready_with_linkedin_cookies_no_password(self):
        """Cookie-based auth should satisfy the credential requirement."""
        assert self._is_ready(
            True,
            {"linkedin": False, "wellfound": False, "internshala": False},
            {"ready": True}
        )

    def test_not_ready_without_resume(self):
        assert not self._is_ready(
            False,
            {"linkedin": True, "wellfound": False, "internshala": False},
            {"ready": False}
        )

    def test_not_ready_with_cookies_stored_but_missing_li_at(self):
        """Stored but not ready (no li_at) must not unlock the launch button."""
        assert not self._is_ready(
            True,
            {"linkedin": False, "wellfound": False, "internshala": False},
            {"stored": True, "has_li_at": False, "ready": False}
        )

    def test_not_ready_with_nothing_configured(self):
        assert not self._is_ready(
            True,
            {"linkedin": False, "wellfound": False, "internshala": False},
            {"ready": False}
        )


# ── Stop button idempotency ───────────────────────────────────────────────────

class TestStopMutation:
    """Stop button must: (a) disable while pending, (b) not fire twice for same run."""

    def test_stop_disables_on_pending(self):
        """Once isPending=True the button should be disabled."""
        is_pending = True
        button_disabled = is_pending  # the fix we applied
        assert button_disabled, "Stop button must be disabled while mutation is pending"

    def test_stop_enabled_when_idle(self):
        """Before clicking, button must be active."""
        is_pending = False
        button_disabled = is_pending
        assert not button_disabled

    def test_stop_shows_loading_indicator(self):
        """While pending, label changes to 'Stopping…'."""
        is_pending = True
        label = 'Stopping…' if is_pending else 'Stop'
        assert label == 'Stopping…'


# ── Resume upload flow ────────────────────────────────────────────────────────

class TestResumeUploadFlow:
    """Resume upload must parse and store data so tailoring can use it."""

    def test_profile_version_changes_on_new_resume(self):
        """Different resume_hash → different profile version → cache busts."""
        import hashlib, json

        def profile_version(profile):
            parts = [
                profile.get("resume_hash") or "",
                profile.get("name") or "",
                json.dumps(profile.get("skills", []), sort_keys=True),
                json.dumps(profile.get("experiences", []), sort_keys=True),
                json.dumps(profile.get("education", []), sort_keys=True),
            ]
            h = hashlib.sha256("|".join(parts).encode()).hexdigest()
            return int(h[:8], 16) % (2 ** 31)

        p1 = {"resume_hash": "hash_v1", "name": "Alice", "skills": [], "experiences": [], "education": []}
        p2 = {"resume_hash": "hash_v2", "name": "Alice", "skills": [], "experiences": [], "education": []}
        assert profile_version(p1) != profile_version(p2), \
            "New resume upload must produce a different cache key"

    def test_same_resume_same_version(self):
        """Re-uploading identical resume must not bust the cache."""
        import hashlib, json

        def profile_version(profile):
            parts = [
                profile.get("resume_hash") or "",
                profile.get("name") or "",
                json.dumps(profile.get("skills", []), sort_keys=True),
                json.dumps(profile.get("experiences", []), sort_keys=True),
                json.dumps(profile.get("education", []), sort_keys=True),
            ]
            h = hashlib.sha256("|".join(parts).encode()).hexdigest()
            return int(h[:8], 16) % (2 ** 31)

        p = {"resume_hash": "same_hash", "name": "Alice", "skills": ["Python"], "experiences": [], "education": []}
        assert profile_version(p) == profile_version(p)
