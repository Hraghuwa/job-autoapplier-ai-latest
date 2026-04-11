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
