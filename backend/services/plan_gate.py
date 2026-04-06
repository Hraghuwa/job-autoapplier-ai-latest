from typing import Optional

PLAN_LIMITS = {
    "free": {
        "platforms": ["linkedin"],
        "applies_per_48hr": 20,
        "cover_letter": False,
        "interview_prep_questions": 3,
        "scheduling": False,
        "analytics": False,
        "kanban": False,
    },
    "pro": {
        "platforms": ["linkedin", "internshala", "naukri", "unstop", "wellfound"],
        "applies_per_48hr": 999999,
        "cover_letter": True,
        "interview_prep_questions": 10,
        "scheduling": True,
        "analytics": True,
        "kanban": True,
    },
    "team": {
        "platforms": ["linkedin", "internshala", "naukri", "unstop", "wellfound"],
        "applies_per_48hr": 999999,
        "cover_letter": True,
        "interview_prep_questions": 10,
        "scheduling": True,
        "analytics": True,
        "kanban": True,
    },
}


def check_plan_access(user_plan: str, feature: str) -> bool:
    limits = PLAN_LIMITS.get(user_plan, PLAN_LIMITS["free"])
    return bool(limits.get(feature, False))


def get_platform_limit(user_plan: str) -> int:
    return PLAN_LIMITS.get(user_plan, PLAN_LIMITS["free"])["applies_per_48hr"]


def allowed_platforms(user_plan: str) -> list:
    return PLAN_LIMITS.get(user_plan, PLAN_LIMITS["free"])["platforms"]
