"""
Celery task that bridges FastAPI → existing Python agents in agents/.

Flow:
  1. Load user config from DB
  2. Check daily quota
  3. Build CONFIG dict matching agents/config.py shape exactly
  4. Monkey-patch agents.config.CONFIG
  5. Call the existing phase function
  6. Stream progress events via Redis pub/sub → WebSocket
"""
from typing import Optional, Dict
import sys
import os
import uuid
import json
import traceback
import threading
from datetime import datetime, date, timedelta

from celery import Task
from celery.utils.log import get_task_logger

from backend.workers.celery_app import celery_app

logger = get_task_logger(__name__)

# ── Stop-event registry ───────────────────────────────────────────────────────
# Maps run_id → threading.Event. Set the event to stop a running phase.
_STOP_EVENTS: Dict[str, threading.Event] = {}

# ── Global CONFIG lock ────────────────────────────────────────────────────────
# Prevents CONFIG race condition when multiple phases run concurrently
# (e.g., if Celery workers share a process, or during test scenarios).
_config_lock = threading.Lock()

def get_stop_event(run_id: str) -> threading.Event:
    """Return existing stop event for run_id, or create one."""
    if run_id not in _STOP_EVENTS:
        _STOP_EVENTS[run_id] = threading.Event()
    return _STOP_EVENTS[run_id]

def request_stop(run_id: str):
    """Signal a running phase to stop at its next loop iteration."""
    ev = _STOP_EVENTS.get(run_id)
    if ev:
        ev.set()

def cleanup_stop_event(run_id: str):
    _STOP_EVENTS.pop(run_id, None)

# ── Redis publisher (sync, used inside Celery worker) ────────────────────────
def _get_redis():
    import redis as _redis
    from backend.config import settings
    return _redis.from_url(settings.redis_url, decode_responses=True)


def _normalize_event(event: dict) -> dict:
    """Convert internal event shape to frontend WSEvent shape.
    Preserves `error_reasons`, `run_id`, and `phase` so the UI can route
    events to the correct run card and render a "why this failed" panel.
    """
    t = event.get("type", "")
    run_id = event.get("run_id")
    phase = event.get("phase")
    if t == "phase_started":
        return {
            "event": "ping",
            "message": f"Starting {event.get('platform', 'agent')}…",
            "run_id": run_id,
            "phase": phase,
        }
    if t == "run_complete":
        return {
            "event": "complete",
            "message": event.get("summary", "Run complete"),
            "applied_count": event.get("total_applied", 0),
            "skipped_count": event.get("total_skipped", 0),
            "error_reasons": event.get("error_reasons", []),
            "run_id": run_id,
            "phase": phase,
        }
    if t == "agent_error":
        return {
            "event": "error",
            "message": event.get("message", "Error"),
            "error_reasons": event.get("error_reasons", []),
            "run_id": run_id,
            "phase": phase,
        }
    if t == "applied":
        return {
            "event": "applied",
            "job_title": event.get("job_title", ""),
            "company": event.get("company", ""),
            "message": event.get("message", ""),
            "run_id": run_id,
        }
    if t == "skipped":
        return {
            "event": "skipped",
            "job_title": event.get("job_title", ""),
            "company": event.get("company", ""),
            "run_id": run_id,
        }
    # Already in frontend format — still make sure run_id is present if caller gave one
    if "event" in event:
        if run_id and "run_id" not in event:
            event["run_id"] = run_id
        return event
    return {"event": "ping", "message": str(event), "run_id": run_id}


def publish(user_id: str, event: dict):
    """Push event to browser — tries Redis first, falls back to in-memory manager."""
    normalized = _normalize_event(event)
    payload = json.dumps(normalized)

    # Try Redis (for Celery workers)
    try:
        r = _get_redis()
        r.publish(f"user:{user_id}:progress", payload)
        return
    except Exception:
        pass

    # Fall back to in-memory WebSocket manager (for background threads)
    try:
        from backend.main import manager
        manager.send_from_thread(user_id, payload)
    except Exception:
        pass


# ── DB helpers (sync SQLAlchemy for Celery worker) ──────────────────────────
def _sync_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.config import settings
    # Convert async URL to sync
    url = settings.database_url.replace("sqlite+aiosqlite", "sqlite").replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    engine = create_engine(url, connect_args={"check_same_thread": False} if "sqlite" in url else {})
    return sessionmaker(bind=engine)()


def _load_user_and_profile(session, user_id: str):
    from backend.models.user import User
    from backend.models.profile import UserProfile
    user = session.query(User).filter(User.id == uuid.UUID(user_id)).first()
    profile = session.query(UserProfile).filter(UserProfile.user_id == uuid.UUID(user_id)).first()
    return user, profile


def _check_quota(session, user_id: str, platform: str, plan: str) -> bool:
    from backend.models.quota import UsageQuota
    from backend.services.plan_gate import PLAN_LIMITS
    today = date.today()
    quota = session.query(UsageQuota).filter(
        UsageQuota.user_id == uuid.UUID(user_id),
        UsageQuota.platform == platform,
        UsageQuota.quota_date == today,
    ).first()
    current = quota.applies_count if quota else 0
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["applies_per_48hr"]
    return current < limit


def _increment_quota(session, user_id: str, platform: str, count: int):
    from backend.models.quota import UsageQuota
    today = date.today()
    quota = session.query(UsageQuota).filter(
        UsageQuota.user_id == uuid.UUID(user_id),
        UsageQuota.platform == platform,
        UsageQuota.quota_date == today,
    ).first()
    if quota:
        quota.applies_count += count
    else:
        quota = UsageQuota(
            user_id=uuid.UUID(user_id),
            platform=platform,
            quota_date=today,
            applies_count=count,
        )
        session.add(quota)
    session.commit()


def _update_run(session, run_id: str, **kwargs):
    from backend.models.agent_run import AgentRun
    run = session.query(AgentRun).filter(AgentRun.id == uuid.UUID(run_id)).first()
    if run:
        for k, v in kwargs.items():
            setattr(run, k, v)
        session.commit()


def _log_event(session, run_id: str, event_type: str, message: str, app_id: Optional[str] = None):
    from backend.models.agent_run import AgentLog
    try:
        log = AgentLog(
            run_id=uuid.UUID(run_id),
            application_id=uuid.UUID(app_id) if app_id else None,
            event_type=event_type,
            message=message[:2048],
        )
        session.add(log)
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass


def _learn_from_run_logs(session, user_id: str, run_id: str) -> Optional[str]:
    """Turn concrete run errors into future custom instructions.

    Best-effort and intentionally non-fatal. If Gemini is unavailable, still
    records a small deterministic rule for common repeat failures.
    """
    from backend.config import settings
    from backend.models.agent_run import AgentLog
    from backend.models.profile import UserProfile
    from sqlalchemy.orm.attributes import flag_modified

    logs = session.query(AgentLog).filter(
        AgentLog.run_id == uuid.UUID(run_id),
        AgentLog.event_type.in_(["error", "login_challenge"]),
    ).order_by(AgentLog.created_at).limit(30).all()
    if not logs:
        return None

    errors_text = "\n".join(f"- {log.message[:500]}" for log in logs)
    advice = ""
    if settings.system_gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.system_gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(f"""You are improving a browser job auto-applier.

These are real failure logs from one run:
{errors_text}

Produce 1-3 concrete future rules. Each rule must be a single imperative sentence.
Return only the rules, one per line.""")
            advice = (response.text or "").strip()
        except Exception as e:
            logger.warning("Self-learning analysis failed for run %s: %s", run_id, e)

    if not advice:
        lowered = errors_text.lower()
        rules = []
        if any(x in lowered for x in ["captcha", "challenge", "checkpoint", "2fa"]):
            rules.append("When a login challenge or CAPTCHA appears, pause the platform flow and ask the user to solve it before retrying.")
        if any(x in lowered for x in ["no apply button", "could not auto-submit", "submit"]):
            rules.append("If the primary apply or submit button is missing, scroll the page and try visible Apply, Submit, Continue, Next, and Send buttons before skipping.")
        if any(x in lowered for x in ["resume", "file", "upload"]):
            rules.append("Before submitting, verify the resume file input accepted the selected resume path; if upload fails, retry once with the static resume.")
        advice = "\n".join(rules[:3])

    if not advice:
        return None

    profile = session.query(UserProfile).filter_by(user_id=uuid.UUID(user_id)).first()
    if not profile:
        return advice
    prefs = _ensure_dict(profile.job_preferences)
    existing = (prefs.get("agent_custom_instructions") or "").strip()
    new_rules = [line.strip("- ").strip() for line in advice.splitlines() if line.strip()]
    added = []
    for rule in new_rules:
        if rule and rule not in existing:
            added.append(rule)
    if not added:
        return advice
    # Audit M3: cap growth. Self-learning appends every run; without a bound the
    # instructions blob grows forever, bloating every future prompt (cost + drift).
    # Keep only the most recent MAX_RULES lines.
    MAX_RULES = 25
    merged = [ln.strip() for ln in (existing.splitlines() + added) if ln.strip()]
    # de-dupe preserving order, then keep the last MAX_RULES
    seen_rules: set = set()
    deduped = []
    for ln in merged:
        if ln not in seen_rules:
            seen_rules.add(ln)
            deduped.append(ln)
    prefs["agent_custom_instructions"] = "\n".join(deduped[-MAX_RULES:]).strip()
    profile.job_preferences = prefs
    flag_modified(profile, "job_preferences")
    session.commit()
    _log_event(session, run_id, "info", f"Self-learning added {len(added)} future rule(s).")
    return "\n".join(added)


def _decrypt(value: str) -> str:
    """Fernet decrypt a stored credential."""
    if not value:
        return ""
    try:
        from backend.services.crypto_service import decrypt
        return decrypt(value)
    except Exception:
        return value  # not encrypted yet


# ── Build CONFIG dict from DB profile ────────────────────────────────────────

_TYPE_SUFFIX = {
    "Internship": "Intern",
    "Trainee":    "Trainee",
    "Fresher":    "Fresher",
    "Full-time":  "",
    "Part-time":  "",
    "Contract":   "",
}
_INTERN_INDICATORS = ["intern", "trainee", "fresher", "apprentice", "graduate"]


def _build_search_keywords(job_titles: list, employment_types: list) -> list:
    """
    Produce clean LinkedIn-ready search keywords from user's job titles + employment types.
    - "Product Manager" + "Internship" → "Product Manager Intern"
    - "Software Engineer" + "Full-time" → "Software Engineer"
    - Already-typed titles ("Product Manager Intern") are used as-is.
    """
    keywords = []
    for title in job_titles:
        title_lower = title.lower()
        already_typed = any(w in title_lower for w in _INTERN_INDICATORS)

        if not employment_types or already_typed:
            keywords.append(title)
        else:
            for etype in employment_types:
                suffix = _TYPE_SUFFIX.get(etype, "")
                if suffix and suffix.lower() not in title_lower:
                    keywords.append(f"{title} {suffix}")
                else:
                    keywords.append(title)

    # Deduplicate preserving order
    seen: set = set()
    out = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


DEFAULT_ROLE_AGENTS = [
    {"name": "Founder Office & PM", "emoji": "🏢", "keywords": [
        "Founder Office Intern", "Founders Office Intern",
        "Product Management Intern", "CEO Office Intern",
        "Chief of Staff Intern", "Business Analyst Intern",
    ]},
    {"name": "Business Strategy", "emoji": "📊", "keywords": [
        "Business Strategist Intern", "Strategy Intern",
        "Strategy Consulting Intern",
    ]},
    {"name": "General Management", "emoji": "📋", "keywords": [
        "Management Trainee", "Management Intern", "Growth Intern",
        "GTM Intern", "Program Manager Intern", "Project Management Intern",
    ]},
]


def _ensure_dict(val) -> dict:
    """SQLAlchemy on SQLite sometimes returns JSON columns as raw strings.
    Also: the parsed JSON might not actually be a dict (legacy data, manual
    inserts, or a column that was seeded with a list/string/null). Callers
    do `.get(...)` on the result and will crash with `'str' object has no
    attribute 'get'` / `'list' object has no attribute 'get'` unless we
    coerce non-dict shapes to an empty dict here.
    """
    if not val:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def is_stopping(run_id: str) -> bool:
    """Non-blocking check used by CLI agents to honour Pause requests.
    Returns True if a stop event exists and has been set for this run_id.
    Also consults Redis `pause:{run_id}` so Celery workers are covered.
    """
    ev = _STOP_EVENTS.get(run_id)
    if ev is not None and ev.is_set():
        return True
    # Redis fallback — cheap and non-blocking
    try:
        import redis as _redis_sync
        from backend.config import settings as _s
        r = _redis_sync.from_url(_s.redis_url, decode_responses=True,
                                 socket_connect_timeout=0.2)
        if r.get(f"pause:{run_id}") == "1":
            return True
    except Exception:
        pass
    return False


def _plan_apply_limit(user) -> int:
    """The user's account-wide daily apply cap from their plan (free=20,
    pro/team effectively unlimited). Falls back to free on any surprise."""
    try:
        from backend.services.plan_gate import PLAN_LIMITS
        plan = getattr(user, "plan", "free") or "free"
        plan = str(plan).split(".")[-1].lower()  # handle PlanEnum.free
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
        return int(limits.get("apply_credits_daily", limits.get("applies_per_48hr", 20)))
    except Exception:
        return 20


def _build_config(user, profile) -> dict:
    prefs = _ensure_dict(profile.job_preferences)
    autofill = _ensure_dict(profile.autofill_bank)
    creds = _ensure_dict(profile.platform_passwords)
    extracted = _ensure_dict(profile.extracted_data)

    def cred(platform, field):
        """Support both nested {platform: {email, password}} and flat {platform_email} formats."""
        # Nested format (seed_admin.py / new onboarding)
        nested = creds.get(platform)
        if isinstance(nested, dict):
            val = nested.get(field, "")
            return _decrypt(val) if val else ""
        # Flat format (legacy)
        return _decrypt(creds.get(f"{platform}_{field}", ""))

    # ── Parse structured resume fields ──────────────────────────────────────────

    # Education: extract individual degree/institution/cgpa/year fields
    edu_list = extracted.get("education", [])
    grad_cgpa = autofill.get("grad_cgpa", "")
    current_cgpa = autofill.get("current_cgpa", "")
    university = autofill.get("university", "")
    degree = autofill.get("degree", "")
    graduation_year = autofill.get("graduation_year", "")
    enrollment_year = autofill.get("enrollment_year", "")
    edu_summary_parts = []
    for edu in edu_list:
        if isinstance(edu, dict):
            d = edu.get("degree", "")
            inst = edu.get("institution", "")
            yr = edu.get("year", "") or ""
            cgpa = edu.get("cgpa") or ""
            if cgpa:
                cgpa = str(cgpa)
            if d and inst:
                edu_summary_parts.append(f"{d} from {inst}{' (' + str(yr) + ')' if yr else ''}{' CGPA: ' + cgpa if cgpa else ''}")
            if not grad_cgpa and cgpa:
                grad_cgpa = str(cgpa)
            if not university and inst:
                university = inst
            if not degree and d:
                degree = d
            if not graduation_year and yr:
                graduation_year = yr
        elif isinstance(edu, str):
            edu_summary_parts.append(edu)
            if not university:
                university = edu

    # Experience: extract company/role/duration for the most recent position
    exp_list = extracted.get("experience", [])
    current_company = autofill.get("current_company", "")
    current_role = autofill.get("current_role", "")
    years_of_experience = autofill.get("years_of_experience", "")
    exp_summary_parts = []
    for exp in exp_list:
        if isinstance(exp, dict):
            co = exp.get("company", "")
            role = exp.get("role", "")
            dur = exp.get("duration", "")
            desc = exp.get("description", "")
            if co or role:
                exp_summary_parts.append(f"{role} at {co}{' (' + dur + ')' if dur else ''}")
            if not current_company and co:
                current_company = co
            if not current_role and role:
                current_role = role
        elif isinstance(exp, str):
            exp_summary_parts.append(exp)
    if not years_of_experience and exp_list:
        years_of_experience = str(len(exp_list))  # rough: 1 entry ≈ 1 role

    # Certifications
    cert_list = extracted.get("certifications", [])
    certifications = autofill.get("certifications", "") or ", ".join(cert_list)

    # Merge autofill_bank + extracted resume data into one rich profile dict
    rich_profile = {
        **autofill,  # user-entered fields take precedence
        "full_name": autofill.get("full_name") or extracted.get("name") or user.name,
        "email": autofill.get("email") or extracted.get("email") or user.email,
        "phone": autofill.get("phone") or extracted.get("phone") or "",
        "linkedin": autofill.get("linkedin") or extracted.get("linkedin_url") or "",
        "location": autofill.get("location") or extracted.get("location") or "",
        "skills": autofill.get("skills") or ", ".join(extracted.get("skills", [])),
        # Structured education fields for form-filling
        "education": "\n".join(edu_summary_parts) if edu_summary_parts else autofill.get("education", ""),
        "university": university,
        "degree": degree,
        "grad_cgpa": grad_cgpa,
        "graduation_cgpa": grad_cgpa,
        "current_cgpa": current_cgpa or grad_cgpa,
        "graduation_year": graduation_year,
        "enrollment_year": enrollment_year,
        # Structured experience fields
        "experience": "\n".join(exp_summary_parts) if exp_summary_parts else autofill.get("experience", ""),
        "experience_summary": "; ".join(exp_summary_parts[:2]) if exp_summary_parts else "",
        "current_company": current_company,
        "current_role": current_role,
        "years_of_experience": years_of_experience,
        # Certifications
        "certifications": certifications,
        "summary": extracted.get("summary", ""),
        # Phase E cache-busting: the tailored_resume_store derives a profile
        # version from these fields so any resume upload or profile edit
        # automatically invalidates the old cached PDFs.
        "resume_hash": str(profile.resume_hash or ""),
        "experiences": extracted.get("experience", []),
    }

    # Build role_agents from user's job_titles + employment_types preferences
    job_titles = prefs.get("job_titles", [])
    employment_types = prefs.get("employment_types", [])
    if job_titles:
        search_keywords = _build_search_keywords(job_titles, employment_types)
        role_agents = [{"name": "User Targets", "emoji": "🎯", "keywords": search_keywords}]
    else:
        search_keywords = prefs.get("keywords", [])
        role_agents = prefs.get("role_agents", DEFAULT_ROLE_AGENTS)

    linkedin_creds = {"email": cred("linkedin", "email"), "password": cred("linkedin", "password")}
    # LinkedIn session cookies — decrypted JSON string. Critical for bypassing
    # the CAPTCHA/security challenge that wipes out password-only logins.
    # Stored under platform_passwords["linkedin_cookies"] by /onboarding/linkedin-cookies.
    linkedin_cookies_raw = creds.get("linkedin_cookies") or ""
    linkedin_cookies_json = _decrypt(linkedin_cookies_raw) if linkedin_cookies_raw else ""
    internshala_creds = {"email": cred("internshala", "email"), "password": cred("internshala", "password")}
    naukri_creds = {"email": cred("naukri", "email"), "password": cred("naukri", "password")}
    unstop_creds = {"email": cred("unstop", "email"), "password": cred("unstop", "password")}
    wellfound_creds = {"email": cred("wellfound", "email"), "password": cred("wellfound", "password")}

    # ──────────────────────────────────────────────────────────────────────────
    # Return a PLAIN dict to avoid pickling/deepcopy locks from SQLAlchemy/ORM.
    # ──────────────────────────────────────────────────────────────────────────
    config = {
        "gemini_api_key": str(_decrypt(user.gemini_key_encrypted or "")) if user.gemini_key_encrypted else "",
        "groq_api_key": str(_decrypt(user.groq_key_encrypted or "")) if user.groq_key_encrypted else "",
        "name": str(rich_profile.get("full_name") or ""),
        "phone": str(rich_profile.get("phone") or ""),
        "email": str(autofill.get("email") or extracted.get("email") or user.email or ""),
        "resume_path": str(profile.resume_url or ""),
        
        "linkedin": linkedin_creds,
        "linkedin_cookies": linkedin_cookies_json,    # raw JSON string for _try_cookie_login
        # user_id is needed by resume_resolver (Phase E) to look up cached
        # tailored PDFs in the store.
        "user_id": user.id,
        "internshala": internshala_creds,
        "naukri": naukri_creds,
        "unstop": unstop_creds,
        "wellfound": wellfound_creds,

        "keywords": list(prefs.get("keywords") or []),
        "locations": list(prefs.get("locations") or []),
        "employment_types": list(prefs.get("employment_types") or []),
        "work_mode": str(prefs.get("work_mode", "Remote")),
        "min_stipend": int(prefs.get("min_stipend", 0)),
        "match_threshold": int(prefs.get("match_threshold", 60)),
        "role_agents": role_agents,

        "profile": dict(rich_profile),
        "cover_letter": str(profile.cover_letter or ""),

        # Account-wide daily apply cap from the user's plan — enforced per-apply
        # by the rate limiter so a single phase can't exceed the plan (the DB
        # quota is only checked at phase start). free=20, pro/team≈unlimited.
        "plan_apply_limit": _plan_apply_limit(user),

        "max_jobs_per_day": int(prefs.get("max_jobs_per_day", 15)),
        "min_per_keyword": 3,
        "delay_between_applies_sec": [10, 25],
        "headless": False,
        "dry_run": False,
        "continuous_mode": True,
        "recently_posted": True,
        # web_search is a DICT (not a bool) — web_search_applier.py:489 calls
        # .get("enabled") on it. A bool here would AttributeError and be silently
        # swallowed by a bare-except in the applier, leaving the phase to return
        # (0, []) with no tabs ever opened. Keep nested options here so the
        # applier can read max_results_per_query/target_companies/ats_domains.
        "web_search": {
            "enabled": bool(prefs.get("disable_web_search", False) is False),
            "max_results_per_query": int(prefs.get("max_results_per_query", 10)),
            "target_companies": list(prefs.get("target_companies") or []),
            "ats_domains": list(prefs.get("ats_domains") or []),
            # User-configurable tab cap (preset options in the UI: 20/50/70/100)
            # and extra sites the user wants searched on top of the defaults.
            # Both are clamped to sane bounds inside web_search_applier.
            "tab_limit": int(prefs.get("web_search_tab_limit", 50)),
            "max_queries": int(prefs.get("web_search_max_queries", 30)),
            # Per-keyword query cap — keeps multi-role searches fair AND bounds
            # the tab fan-out (each keyword × this many queries × ~10 links).
            "max_queries_per_keyword": int(prefs.get("web_search_max_queries_per_keyword", 6)),
            "google_login_wait_sec": int(prefs.get("google_login_wait_sec", 120)),
            "extra_sites": list(prefs.get("web_search_extra_sites") or []),
        },
        "custom_instructions": str(prefs.get("agent_custom_instructions", "")),
    }
    return config


# ── stdout → WS-event classifier (pure; unit-tested) ─────────────────────────
# Markers that mean "the agent is stuck at a human-solvable login/captcha step",
# NOT a crash. When any of these appear with a ❌, we emit `login_challenge`
# (actionable) instead of `error` (toast spam).
CHALLENGE_MARKERS = (
    "security challenge", "captcha", "checkpoint", "2fa", "two-factor",
    "two factor", "verify it's you", "verify its you",
    "🚨",  # other_platforms.py uses 🚨 as the CAPTCHA prefix
    "challenge detected", "challenge not resolved", "solve it manually",
)
PLATFORM_HINTS = ("linkedin", "internshala", "unstop", "naukri", "wellfound", "google")

PHASE_PLATFORM_MAP = {
    1: "linkedin", 2: "internshala", 3: "wellfound", 4: "naukri",
    5: "unstop", 6: "web_search", 7: "form_fill",
}


def classify_agent_line(line: str):
    """Classify one printed agent line into a WS event.

    Pure function (no I/O) so it can be unit-tested and reused by both the
    in-process path and the subprocess stdout reader. Returns a dict
    {"category", "event"} (event has no run_id — the caller adds it), or None.
    Order matters: applied/skipped first, then login_challenge (must beat the
    generic "❌ = error" rule), then generic error, then ping.
    """
    line = (line or "").strip()
    if not line:
        return None
    ll = line.lower()
    has_challenge_marker = any(m in ll for m in CHALLENGE_MARKERS)
    is_login_msg = ("login" in ll or has_challenge_marker)
    has_failure = ("❌" in line or "failed" in ll or "error" in ll)
    # Audit N2: an explicit challenge marker (🚨 CAPTCHA, "security challenge",
    # "solve it manually", …) is actionable on its own — other_platforms.py
    # prints these WITHOUT a ❌. The bare word "login" still needs a failure
    # marker so routine "Logging in..." lines don't spam login_challenge.
    is_login_blocked = has_challenge_marker or (has_failure and is_login_msg)
    is_error = has_failure and not is_login_msg

    if "External form filled" in line or "✅ Applied" in line:
        return {"category": "applied", "event": {"event": "applied", "message": line}}
    if "⏭" in line or "Already applied" in line or "Skipping" in line:
        return {"category": "skipped", "event": {"event": "skipped", "message": line}}
    if is_login_blocked:
        hint = next((p for p in PLATFORM_HINTS if p in ll), "unknown")
        return {"category": "login_challenge", "platform_hint": hint, "event": {
            "event": "login_challenge", "platform": hint, "message": line,
            "action_required": (f"Open the Chrome window and solve the {hint} "
                                 f"security challenge manually, then click Run again."),
        }}
    if is_error:
        return {"category": "error", "event": {"event": "error", "message": line}}
    if "🎯 KEYWORD" in line or "LINKEDIN AGENT" in line or "Phase" in line:
        return {"category": "ping", "event": {"event": "ping", "message": line}}
    return None


def _redis_paused(run_id: str) -> bool:
    try:
        import redis as _r
        from backend.config import settings as _s
        c = _r.from_url(_s.redis_url, decode_responses=True, socket_connect_timeout=0.2)
        return c.get(f"pause:{run_id}") == "1"
    except Exception:
        return False


# ── In-process executor (legacy path; escape hatch via JOBAGENT_INPROC_PHASE=1) ─
# Audit C2: the default path now runs each phase in an isolated subprocess
# (_execute_subprocess) so there is NO process-global CONFIG, NO global stdout
# swap, and NO global lock serialising every user's run. This in-process path is
# preserved for emergencies and selected with JOBAGENT_INPROC_PHASE=1; it still
# uses the global lock because it shares the module-global CONFIG.
def _execute_inproc(user_id, phase, run_id, config, dry_run, session, on_line, stop_event) -> int:
    import importlib
    applied = 0

    class _Cap:
        def __init__(self, orig):
            self._orig = orig
            self._buf = ""
        def write(self, text):
            self._orig.write(text)
            self._buf += text
            if "\n" in self._buf:
                parts = self._buf.split("\n")
                self._buf = parts[-1]
                for ln in parts[:-1]:
                    on_line(ln)
        def flush(self):
            self._orig.flush()

    _orig_stdout = sys.stdout
    sys.stdout = _Cap(_orig_stdout)
    try:
        agents_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents"))
        if agents_path not in sys.path:
            sys.path.insert(0, agents_path)
        for _mod in ['run_phase1', 'orchestrator', 'main', 'linkedin_applier',
                     'wellfound_applier', 'web_search_applier', 'google_form_filler',
                     'other_platforms', 'job_finder']:
            sys.modules.pop(_mod, None)

        config_snapshot = config.copy()
        config_snapshot["_server_mode"] = True
        config_snapshot["_stop_event"] = stop_event
        config_snapshot["current_run_id"] = run_id
        _safe_suffix = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(user_id))
        config_snapshot["chrome_profile_suffix"] = _safe_suffix

        from backend.database import engine as _async_engine
        from sqlalchemy import create_engine as _create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker
        try:
            sync_url = str(_async_engine.url).replace("+aiosqlite", "").replace("+asyncpg", "")
            _sync_eng = _create_engine(sync_url, future=True)
            config_snapshot["_session_factory"] = _sessionmaker(_sync_eng, expire_on_commit=False)
            config_snapshot["_tailored_upload_dir"] = os.environ.get(
                "TAILORED_UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "tailored"))
        except Exception as _e:
            logger.warning("Could not build sync session factory for tailoring: %s", _e)

        def _save_linkedin_cookies(fresh_json: str, _uid=str(user_id)) -> None:
            try:
                from backend.models.profile import UserProfile as _UP
                from sqlalchemy.orm.attributes import flag_modified as _fm
                from backend.services.crypto_service import encrypt as _enc
                _s = _sync_session()
                try:
                    _prof = _s.query(_UP).filter_by(user_id=uuid.UUID(_uid)).first()
                    if _prof:
                        _creds = dict(_prof.platform_passwords or {})
                        _creds["linkedin_cookies"] = _enc(fresh_json)
                        _prof.platform_passwords = _creds
                        _fm(_prof, "platform_passwords")
                        _s.commit()
                finally:
                    _s.close()
            except Exception as _err:
                logger.warning("Could not refresh LinkedIn cookies: %s", _err)
        config_snapshot["_save_linkedin_cookies"] = _save_linkedin_cookies

        agent_config_mod = importlib.import_module("config")
        for k, v in config_snapshot.items():
            setattr(agent_config_mod, k, v)

        with _config_lock:
            agent_config_mod.CONFIG.clear()
            agent_config_mod.CONFIG.update(config_snapshot)
            applied = _dispatch_phase(phase) or 0
            if phase == 7:
                _persist_autofill_bank(session, user_id, agent_config_mod)
        return applied
    finally:
        sys.stdout = _orig_stdout


def _dispatch_phase(phase: int) -> int:
    if phase == 1:
        from run_phase1 import main as phase_fn
        return phase_fn() or 0
    if phase == 2:
        from orchestrator import run_internshala_phase
        return run_internshala_phase()
    if phase == 3:
        from orchestrator import run_wellfound_phase
        return run_wellfound_phase()
    if phase == 4:
        from orchestrator import run_naukri_phase
        return run_naukri_phase()
    if phase == 5:
        from orchestrator import run_unstop_phase
        return run_unstop_phase()
    if phase == 6:
        from orchestrator import run_web_search_phase
        return run_web_search_phase()
    if phase == 7:
        from orchestrator import run_form_fill_phase
        return run_form_fill_phase()
    return 0


def _persist_autofill_bank(session, user_id, agent_config_mod) -> None:
    try:
        learned_bank = agent_config_mod.CONFIG.get("autofill_bank", {})
        if not learned_bank:
            return
        from backend.models.profile import UserProfile
        prof = session.query(UserProfile).filter_by(user_id=uuid.UUID(str(user_id))).first()
        if prof:
            existing = prof.autofill_bank or {}
            existing.update(learned_bank)
            prof.autofill_bank = existing
            session.commit()
            logger.info("Persisted %d autofill entries for user %s", len(learned_bank), user_id)
    except Exception as _e:
        logger.warning("Could not persist autofill bank: %s", _e)


def _get_python_executable() -> str:
    """Resolve correct virtualenv python binary on macOS / Windows."""
    py_exe = sys.executable
    if sys.prefix != sys.base_prefix:
        venv_py = os.path.join(sys.prefix, "bin", "python")
        if os.path.exists(venv_py):
            return venv_py
        venv_py_win = os.path.join(sys.prefix, "Scripts", "python.exe")
        if os.path.exists(venv_py_win):
            return venv_py_win
    return py_exe


# ── Subprocess executor (default) — full isolation, no globals, no lock ──────
def _execute_subprocess(user_id, phase, run_id, config, dry_run, on_line) -> int:
    import subprocess
    import tempfile
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    script = os.path.join(repo_root, "agents", "run_phase_subprocess.py")

    cfg = dict(config)
    cfg["user_id"] = str(config.get("user_id") or user_id)
    cfg["run_id"] = run_id
    cfg["dry_run"] = bool(dry_run)

    applied = 0
    with tempfile.TemporaryDirectory(prefix=f"jobrun_{run_id}_") as td:
        cfg_path = os.path.join(td, "config.json")
        res_path = os.path.join(td, "result.json")
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, default=str)

        env = {**os.environ, "PYTHONUNBUFFERED": "1", "JOBAGENT_SERVER_MODE": "1"}
        py_exe = _get_python_executable()
        proc = subprocess.Popen(
            [py_exe, script, cfg_path, str(phase), run_id, res_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=repo_root, env=env,
        )
        try:
            for line in proc.stdout:  # streams live; classifier runs per line
                on_line(line.rstrip("\n"))
        finally:
            proc.wait()
        try:
            with open(res_path) as f:
                applied = int(json.load(f).get("applied") or 0)
        except Exception:
            logger.warning("Subprocess produced no result file for run %s (exit=%s)",
                           run_id, proc.returncode)
    return applied


# ── Core logic (callable directly or via Celery) ─────────────────────────────
def _run_phase_logic(user_id: str, phase: int, run_id: str, task_self=None, dry_run: bool = False):
    import sys as _sys  # noqa: F401 — kept for parity; sys imported at module top
    session = _sync_session()
    applied = 0
    skipped = 0
    errors = 0
    error_reasons: list = []  # collect error messages for post-run summary
    stats = {"skipped": 0, "errors": 0}

    # Create a stop event for this run — used by the in-process path; the
    # subprocess path honours stop via the Redis pause:{run_id} key.
    stop_event = get_stop_event(run_id)

    try:
        user, profile = _load_user_and_profile(session, user_id)
        if not user or not profile:
            _update_run(session, run_id, status="failed", completed_at=datetime.utcnow())
            return

        platform = PHASE_PLATFORM_MAP.get(phase, "unknown")

        # Quota check
        if not _check_quota(session, user_id, platform, user.plan):
            _update_run(session, run_id, status="limit_reached", completed_at=datetime.utcnow())
            publish(user_id, {"type": "run_complete", "message": "Daily limit reached."})
            return

        celery_task_id = task_self.request.id if task_self else None
        _update_run(session, run_id, status="running", started_at=datetime.utcnow(),
                    celery_task_id=celery_task_id)
        _log_event(session, run_id, "info", f"Phase {phase} ({platform}) started.")
        publish(user_id, {"type": "phase_started", "phase": phase, "platform": platform,
                          "run_id": run_id})

        # Per-line handler: classify → log + publish + accumulate stats. Shared
        # by both executors so behaviour is identical regardless of path.
        def _handle_line(line):
            res = classify_agent_line(line)
            if not res:
                return
            cat = res["category"]
            event = dict(res["event"])
            event["run_id"] = run_id
            if cat == "applied":
                _log_event(session, run_id, "applied", line)
            elif cat == "skipped":
                stats["skipped"] += 1
                _log_event(session, run_id, "skipped", line)
            elif cat == "login_challenge":
                stats["errors"] += 1
                _log_event(session, run_id, "login_challenge", line)
                error_reasons.append(f"LOGIN CHALLENGE [{res.get('platform_hint','unknown')}]: {line[:200]}")
            elif cat == "error":
                stats["errors"] += 1
                _log_event(session, run_id, "error", line)
                error_reasons.append(line[:200])
            elif cat == "ping":
                _log_event(session, run_id, "info", line)
            publish(user_id, event)

        config = _build_config(user, profile)
        config["run_id"] = run_id
        config["dry_run"] = bool(dry_run)

        if os.environ.get("JOBAGENT_INPROC_PHASE") == "1":
            applied = _execute_inproc(user_id, phase, run_id, config, dry_run,
                                      session, _handle_line, stop_event)
        else:
            applied = _execute_subprocess(user_id, phase, run_id, config, dry_run, _handle_line)

        skipped = stats["skipped"]
        errors = stats["errors"]
        _increment_quota(session, user_id, platform, applied)
        was_stopped = stop_event.is_set() or _redis_paused(run_id)
        final_status = "paused" if was_stopped else "completed"
        _log_event(session, run_id, "info", f"Phase {phase} {'stopped' if was_stopped else 'completed'}. Applied: {applied}")
        try:
            learned = _learn_from_run_logs(session, user_id, run_id)
            if learned:
                logger.info("Self-learning rules for run %s:\n%s", run_id, learned)
        except Exception as _learn_err:
            logger.warning("Self-learning skipped for run %s: %s", run_id, _learn_err)
        _update_run(session, run_id, status=final_status, completed_at=datetime.utcnow(),
                    applied_count=applied, skipped_count=skipped, error_count=errors)
        publish(user_id, {
            "type": "run_complete",
            "phase": phase,
            "run_id": run_id,
            "total_applied": applied,
            "total_skipped": skipped,
            "error_reasons": error_reasons[-10:],  # last 10 errors max
            "summary": f"Stopped by user — {applied} applied." if was_stopped else f"Phase {phase} done — {applied} applications submitted.",
        })

    except Exception as e:
        # Executors restore their own stdout in a finally; nothing to undo here.
        tb = traceback.format_exc()
        logger.error(f"Phase {phase} failed for user {user_id}: {e}\n{tb}")
        _log_event(session, run_id, "error", f"{e}\n{tb}"[:2000])
        try:
            _learn_from_run_logs(session, user_id, run_id)
        except Exception as _learn_err:
            logger.warning("Self-learning skipped for failed run %s: %s", run_id, _learn_err)
        _update_run(session, run_id, status="failed", completed_at=datetime.utcnow(),
                    error_count=1)
        publish(user_id, {
            "type": "agent_error",
            "phase": phase,
            "run_id": run_id,
            "message": str(e),
            "error_reasons": (error_reasons[-5:] if error_reasons else []) + [str(e)[:200]],
        })
    finally:
        session.close()
        cleanup_stop_event(run_id)


# ── Celery task wrapper ───────────────────────────────────────────────────────
@celery_app.task(bind=True, name="backend.workers.agent_tasks.run_phase_task", max_retries=0)
def run_phase_task(self: Task, user_id: str, phase: int, run_id: str, dry_run: bool = False):
    _run_phase_logic(user_id, phase, run_id, task_self=self, dry_run=dry_run)


@celery_app.task(name="backend.workers.agent_tasks.check_schedules")
def check_schedules():
    from backend.models.user import User
    from backend.models.profile import UserProfile
    from backend.models.agent_run import AgentRun, RunStatus
    session = _sync_session()
    
    try:
        users = session.query(User).join(UserProfile).all()
        for user in users:
            profile = session.query(UserProfile).filter_by(user_id=user.id).first()
            if not profile or not profile.job_preferences:
                continue
            
            schedule = profile.job_preferences.get("schedule", {})
            if not schedule or not schedule.get("enabled"):
                continue
                
            # Audit M4: use croniter for correct cron matching when available;
            # fall back to the legacy hour-only check otherwise. Beat is assumed
            # to call this ~hourly, so we match the cron against the current hour
            # window. The per-day dedup below prevents double-fires either way.
            cron = schedule.get("cron", "0 9 * * *")
            now = datetime.now()
            should_fire = None
            try:
                from croniter import croniter as _croniter
                # True iff the cron's most-recent scheduled time falls within this hour.
                prev = _croniter(cron, now).get_prev(datetime)
                should_fire = (now - prev) < timedelta(hours=1)
            except Exception:
                should_fire = None  # croniter unavailable / bad expr → use fallback

            if should_fire is None:
                parts = cron.split(" ")
                if len(parts) >= 2:
                    target_hour = parts[1]
                    if target_hour != "*" and str(now.hour) != target_hour:
                        continue  # not time yet
            elif not should_fire:
                continue

            phases = schedule.get("phases", [])
            for phase in phases:
                # To prevent running multiple times an hour, check if already ran today
                run = session.query(AgentRun).filter(
                    AgentRun.user_id == user.id,
                    AgentRun.phase == phase,
                    AgentRun.started_at >= date.today()
                ).first()
                
                if not run:
                    run_id = str(uuid.uuid4())
                    new_run = AgentRun(
                        id=uuid.UUID(run_id),
                        user_id=user.id,
                        phase=phase,
                        status=RunStatus.queued,
                    )
                    session.add(new_run)
                    session.commit()
                    run_phase_task.apply_async(args=[str(user.id), phase, run_id], queue="agents")
                    logger.info(f"Scheduled phase {phase} for user {user.id}")
    except Exception as e:
        logger.error(f"Error checking schedules: {e}")
    finally:
        session.close()
