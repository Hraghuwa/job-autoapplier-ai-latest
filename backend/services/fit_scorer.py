"""Pre-apply fit scorer — the agents' decision engine (PLAN §1 match gate).

Before this, the appliers applied to every job their title search returned. That
wastes the three scarce resources the product depends on: daily applies (the
ban-safety budget), LLM tokens (tailoring cost), and the user's credibility with
each platform. score_fit() lets an applier *think before it spends*: it combines
must-have coverage, title/keyword overlap, seniority sanity, and hard red-flag
vetoes into a single 0–100 score + apply/skip decision with human-readable
reasons (surfaced in the run log so the user sees WHY a job was skipped).

Pure function over a JDSignature + profile dict — no I/O, no browser, fully
unit-tested. Never raises.

Weighting (sums to 100 before red-flag handling):
    must_have_coverage  55   — can the candidate actually do the job?
    title_match         25   — is this even the right kind of role?
    seniority_fit       20   — intern applying to staff = wasted shot
Hard red flags (unpaid, scam, pay-to-apply, MLM) veto outright → score 0, skip.
Soft/vague red flags apply a small penalty, no veto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_FLOOR = 55

# Red flags that should ALWAYS skip, no matter how good the skills match.
_HARD_RED_FLAGS = (
    "unpaid", "no pay", "no stipend", "non-paying", "without pay",
    "pay to apply", "registration fee", "pay a fee", "security deposit",
    "mlm", "multi-level", "pyramid", "commission only", "scam",
)

_SENIORITY_RANK = {
    "intern": 0, "junior": 1, "mid": 2, "senior": 3, "staff": 4, "lead": 4,
    "unknown": 2,
}

_STOPWORDS = {"the", "a", "an", "of", "for", "and", "to", "in", "at", "intern",
              "internship", "job", "role", "position", "remote", "fulltime",
              "full", "time", "part"}


@dataclass
class FitDecision:
    score: int
    apply: bool
    vetoed: bool
    reasons: List[str] = field(default_factory=list)
    components: Dict[str, float] = field(default_factory=dict)


def _as_skill_set(value: Any) -> set:
    if isinstance(value, str):
        parts = re.split(r"[,;\n/|]", value)
    elif isinstance(value, list):
        parts = [str(v) for v in value]
    else:
        return set()
    return {p.strip().lower() for p in parts if p and p.strip()}


def _profile_text(profile: Dict[str, Any]) -> str:
    """Flatten skills + experience bullets into one lowercase haystack."""
    chunks: List[str] = []
    skills = profile.get("skills")
    if isinstance(skills, str):
        chunks.append(skills)
    elif isinstance(skills, list):
        chunks.extend(str(s) for s in skills)
    exp = profile.get("experience")
    if isinstance(exp, list):
        for e in exp:
            if isinstance(e, dict):
                chunks.append(str(e.get("role", "")))
                for b in (e.get("bullets") or []):
                    if isinstance(b, dict):
                        chunks.append(str(b.get("text", "")))
                    else:
                        chunks.append(str(b))
            else:
                chunks.append(str(e))
    for k in ("summary", "experience_summary", "current_role"):
        v = profile.get(k)
        if isinstance(v, str):
            chunks.append(v)
    return " ".join(chunks).lower()


def _covers(term: str, haystack_words: set, haystack_text: str) -> bool:
    """A must-have is 'covered' if it (or its head token >=4 chars) appears."""
    t = term.strip().lower()
    if not t:
        return True
    if t in haystack_text:
        return True
    for tok in re.split(r"\W+", t):
        if len(tok) >= 4 and (tok in haystack_words or tok in haystack_text):
            return True
    return False


def _must_have_coverage(must_haves: List[str], profile: Dict[str, Any]) -> float:
    if not must_haves:
        return 1.0  # JD makes no hard demands → nothing to miss
    text = _profile_text(profile)
    words = set(re.split(r"\W+", text))
    hits = sum(1 for m in must_haves if _covers(m, words, text))
    return hits / len(must_haves)


def _title_match(keywords: List[str], title: Optional[str], profile: Dict[str, Any]) -> float:
    if not title:
        return 0.5  # unknown title — neutral, don't punish
    title_words = {w for w in re.split(r"\W+", title.lower()) if w and w not in _STOPWORDS}
    if not title_words:
        return 0.5
    signal = {w.lower() for kw in (keywords or []) for w in re.split(r"\W+", kw)
              if len(w) >= 3 and w.lower() not in _STOPWORDS}
    signal |= _as_skill_set(profile.get("skills"))
    if not signal:
        return 0.5
    overlap = sum(1 for w in title_words if any(w.startswith(s[:5]) or s.startswith(w[:5]) for s in signal))
    return min(1.0, overlap / max(1, len(title_words)))


def _seniority_fit(jd_seniority: str, profile: Dict[str, Any]) -> float:
    jd_rank = _SENIORITY_RANK.get((jd_seniority or "unknown").lower(), 2)
    try:
        years = float(profile.get("years_of_experience") or 0)
    except (TypeError, ValueError):
        years = 0.0
    # Map candidate years → an approximate rank.
    cand_rank = 0 if years < 1 else 1 if years < 3 else 2 if years < 6 else 3
    gap = abs(jd_rank - cand_rank)
    return max(0.0, 1.0 - 0.34 * gap)  # 0 gap=1.0, 1=0.66, 2=0.32, 3=0.0


def score_fit(jd_sig, profile: Dict[str, Any], *, title: Optional[str] = None,
              floor: int = DEFAULT_FLOOR) -> FitDecision:
    """Decide whether to apply. Never raises."""
    try:
        profile = profile if isinstance(profile, dict) else {}
        must_haves = list(getattr(jd_sig, "must_haves", []) or [])
        keywords = list(getattr(jd_sig, "keywords", []) or [])
        red_flags = list(getattr(jd_sig, "red_flags", []) or [])
        seniority = getattr(jd_sig, "seniority", "unknown")

        # Hard red-flag veto first — parsimony: don't even score a scam.
        flags_text = " ".join(str(f).lower() for f in red_flags)
        hard = [f for f in _HARD_RED_FLAGS if f in flags_text]
        if hard:
            return FitDecision(
                score=0, apply=False, vetoed=True,
                reasons=[f"Hard red flag — skipped (matched: {', '.join(hard)})."],
                components={"must_have_coverage": 0.0, "title_match": 0.0,
                            "seniority_fit": 0.0, "red_flag_penalty": 1.0},
            )

        cov = _must_have_coverage(must_haves, profile)
        tit = _title_match(keywords, title, profile)
        sen = _seniority_fit(seniority, profile)
        soft_penalty = 0.10 if red_flags else 0.0  # vague flags nudge down

        raw = (cov * 55) + (tit * 25) + (sen * 20)
        score = int(round(max(0.0, raw * (1.0 - soft_penalty))))

        reasons: List[str] = []
        reasons.append(f"Must-have coverage {cov*100:.0f}% (weight 55).")
        reasons.append(f"Title/keyword match {tit*100:.0f}% (weight 25).")
        reasons.append(f"Seniority fit {sen*100:.0f}% (weight 20).")
        if red_flags:
            reasons.append(f"Soft red flags noted: {', '.join(map(str, red_flags))}.")

        apply = score >= floor
        reasons.append(f"Score {score} {'>=' if apply else '<'} floor {floor} → "
                       f"{'APPLY' if apply else 'SKIP'}.")
        return FitDecision(
            score=score, apply=apply, vetoed=False, reasons=reasons,
            components={"must_have_coverage": round(cov, 3),
                        "title_match": round(tit, 3),
                        "seniority_fit": round(sen, 3),
                        "red_flag_penalty": soft_penalty},
        )
    except Exception:
        # Decision engine must never break an applier — fail OPEN to a neutral
        # apply so a scorer bug degrades to today's behaviour, not a halt.
        return FitDecision(score=floor, apply=True, vetoed=False,
                           reasons=["fit_scorer error — defaulted to apply."],
                           components={"must_have_coverage": 1.0, "title_match": 0.5,
                                       "seniority_fit": 0.5, "red_flag_penalty": 0.0})
