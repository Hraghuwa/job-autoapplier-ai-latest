"""Decide whether a posting is worth a tab, BEFORE opening it (ADR-001).

Pure rules over title / location / profile — no browser, no LLM, never raises.
The LLM fit gate (backend.services.apply_decision) runs after this on the
survivors that carry JD text.
"""
import re

LEVELS = ["intern", "entry", "associate", "mid", "senior", "lead", "director"]

# Checked top-down; first hit wins. Patterns are whole-word.
_LEVEL_PATTERNS = [
    ("director", r"director|head of|vice president|vp|chief|cxo|principal|partner"),
    ("lead", r"lead|staff|team lead|group manager"),
    ("senior", r"senior|sr|manager ii|manager iii|expert"),
    ("intern", r"intern|internship|trainee|apprentice"),
    ("associate", r"associate|assistant manager|analyst|coordinator|specialist"),
    ("entry", r"junior|jr|entry|fresher|graduate|executive|assistant|representative|i"),
    ("mid", r"manager|consultant|ii|iii"),
]

_TECH = r"engineer|engineering|developer|devops|sre|architect|scientist|programmer|machine learning|ml|backend|frontend|full ?stack|data platform|security engineer"
_TECH_SKILLS = r"python|java|javascript|react|node|golang|kubernetes|aws|machine learning|software"

_STOP = {"the", "and", "of", "a", "an", "for", "to", "in", "at", "with"}

# Remote postings restricted to these regions are not applyable from India.
_FOREIGN_ONLY = r"united states|\bus\b|\busa\b|canada|united kingdom|\buk\b|ireland|israel|germany|europe|emea|north america|latam|australia|japan|singapore|france|netherlands|spain|poland"


def _has(pattern, text):
    return re.search(rf"\b(?:{pattern})\b", text) is not None


def title_level(title):
    t = (title or "").lower()
    for level, pat in _LEVEL_PATTERNS:
        if _has(pat, t):
            return level
    return "mid"  # bare titles like "Product Manager" / "Consultant"


def role_matches(title, keywords):
    """Every significant word of at least one keyword appears as a whole word."""
    words = set(re.findall(r"[a-z]+", (title or "").lower()))
    for kw in keywords or []:
        toks = [w for w in re.findall(r"[a-z]+", kw.lower()) if w not in _STOP]
        # plural / -er tolerance: "operation" matches "operations"
        if toks and all(any(w == t or w == t + "s" or t == w + "s" for w in words) for t in toks):
            return True
    return False


def is_tech_title(title):
    return _has(_TECH, (title or "").lower())


def profile_is_tech(profile):
    p = profile or {}
    blob = " ".join(str(p.get(k) or "") for k in ("skills", "current_role", "summary", "experience_summary"))
    return _has(_TECH_SKILLS, blob.lower()) or _has(_TECH, blob.lower())


def location_ok(location, locations):
    loc = (location or "").lower()
    if not loc:
        return True  # unknown → let the LLM gate / user decide
    if "india" in loc or any(c.lower() in loc for c in (locations or []) if c.lower() != "remote"):
        return True
    if "remote" in loc or "anywhere" in loc:
        return not _has(_FOREIGN_ONLY, loc)
    return False


def target_ctx(config):
    """Everything the rules need, derived once from the run config."""
    config = config or {}
    keywords = []
    for agent in config.get("role_agents") or []:
        keywords += [k for k in agent.get("keywords") or [] if k and k not in keywords]
    keywords += [k for k in config.get("keywords") or [] if k and k not in keywords]
    target = str(config.get("target_seniority") or "entry").lower()
    max_level = LEVELS.index(target) if target in LEVELS else LEVELS.index("entry")
    # "entry" also allows associate/analyst titles — the realistic band for a
    # career switcher with a few years of non-tech experience.
    if target == "entry":
        max_level = LEVELS.index("associate")
    return {
        "keywords": keywords,
        "locations": config.get("locations") or [],
        "max_level": max_level,
        "allow_tech": profile_is_tech(config.get("profile")),
    }


def check(title, location, ctx):
    """(ok, reason). reason explains a skip in one short phrase."""
    if not role_matches(title, ctx["keywords"]):
        return False, "role doesn't match your target titles"
    level = title_level(title)
    if LEVELS.index(level) > ctx["max_level"]:
        return False, f"{level}-level role, above your target"
    if is_tech_title(title) and not ctx["allow_tech"]:
        return False, "tech role, profile isn't technical"
    if not location_ok(location, ctx["locations"]):
        return False, f"location '{(location or '')[:40]}' outside your locations"
    return True, "ok"
