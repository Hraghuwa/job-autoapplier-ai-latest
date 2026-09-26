from typing import Optional

# ── Plan definitions ──────────────────────────────────────────────────────────
# ai_tokens_monthly  : Gemini calls per calendar month (cover letter, form-fill AI, vision)
# apply_credits_daily: apply actions per 48-hour window
# web_search_platforms: all 30+ boards via Phase 2 (unlocked on pro)
PLAN_LIMITS = {
    "free": {
        "platforms": ["linkedin"],
        "applies_per_48hr": 20,
        "ai_tokens_monthly": 50,
        "apply_credits_daily": 20,
        "web_search": False,
        "cover_letter": False,
        "interview_prep_questions": 3,
        "scheduling": False,
        "analytics": False,
        "kanban": False,
        "tab_limit": 20,
    },
    "pro": {
        "platforms": ["linkedin", "internshala", "naukri", "unstop", "wellfound", "web_search"],
        "applies_per_48hr": 999999,
        "ai_tokens_monthly": 2000,
        "apply_credits_daily": 999999,
        "web_search": True,
        "cover_letter": True,
        "interview_prep_questions": 10,
        "scheduling": True,
        "analytics": True,
        "kanban": True,
        "tab_limit": 100,
    },
    "team": {
        "platforms": ["linkedin", "internshala", "naukri", "unstop", "wellfound", "web_search"],
        "applies_per_48hr": 999999,
        "ai_tokens_monthly": 5000,
        "apply_credits_daily": 999999,
        "web_search": True,
        "cover_letter": True,
        "interview_prep_questions": 10,
        "scheduling": True,
        "analytics": True,
        "kanban": True,
        "tab_limit": 100,
    },
}


def check_plan_access(user_plan: str, feature: str) -> bool:
    limits = PLAN_LIMITS.get(user_plan, PLAN_LIMITS["free"])
    return bool(limits.get(feature, False))


def get_platform_limit(user_plan: str) -> int:
    return PLAN_LIMITS.get(user_plan, PLAN_LIMITS["free"])["applies_per_48hr"]


def allowed_platforms(user_plan: str) -> list:
    return PLAN_LIMITS.get(user_plan, PLAN_LIMITS["free"])["platforms"]


def consume_ai_token(user) -> None:
    """Meter one AI call billed to the OPERATOR's key.

    Users with their own Gemini/Groq key are not charged. Otherwise the call
    costs one `ai_tokens_balance` unit; at 0 we refuse (402) so a single account
    can't drain the system key. Balances top up monthly to the plan allowance
    (never lowered, so purchased tokens survive the reset). Mutates `user`;
    the request's get_db session commits it.
    """
    from datetime import datetime, timedelta
    from fastapi import HTTPException

    if user is None or getattr(user, "gemini_key_encrypted", None) or getattr(user, "groq_key_encrypted", None):
        return
    plan = str(getattr(user, "plan", "free") or "free").split(".")[-1].lower()
    monthly = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["ai_tokens_monthly"]
    now = datetime.utcnow()
    if user.tokens_reset_at is None or user.tokens_reset_at <= now:
        user.ai_tokens_balance = max(user.ai_tokens_balance or 0, monthly)
        user.tokens_reset_at = now + timedelta(days=30)
    if (user.ai_tokens_balance or 0) <= 0:
        raise HTTPException(402, "AI token balance exhausted. Add your own Gemini/Groq key in Settings, or upgrade.")
    user.ai_tokens_balance -= 1
