"""Phase F — Per-resume / per-archetype response-rate aggregations.

Reads applications + job_outcomes + tailored_resumes, returns rolled-up
metrics for the UI's Patterns tab.

A "callback" is any outcome that is more positive than 'applied'/'rejected':
    viewed | shortlisted | interview | offer
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

CALLBACK_OUTCOMES = ("viewed", "shortlisted", "interview", "offer")


def _callback_set_sql() -> str:
    """SQL fragment matching JobOutcome.outcome IN (callbacks). Parameterised."""
    return "(" + ",".join(f"'{o}'" for o in CALLBACK_OUTCOMES) + ")"


def _uid_param(user_id) -> str:
    """Normalise to the 32-char hex form SQLAlchemy uses for SQLite UUIDs."""
    if hasattr(user_id, "hex"):
        return user_id.hex
    s = str(user_id).replace("-", "")
    return s


def by_tailored_resume(session: Session, user_id) -> List[Dict[str, Any]]:
    """One row per tailored_resume_id: applied / callbacks / response_rate."""
    sql = text(f"""
        SELECT
            a.tailored_resume_id           AS tid,
            tr.jd_signature                AS sig,
            COUNT(a.id)                    AS applied,
            SUM(CASE WHEN o.outcome IN {_callback_set_sql()} THEN 1 ELSE 0 END) AS callbacks
        FROM applications a
        LEFT JOIN job_outcomes  o  ON o.application_id    = a.id
        LEFT JOIN tailored_resumes tr ON tr.id            = a.tailored_resume_id
        WHERE (a.user_id = :uid OR a.user_id = :uid_dashed)
          AND a.tailored_resume_id IS NOT NULL
        GROUP BY a.tailored_resume_id
    """)
    uid = _uid_param(user_id)
    rows = session.execute(sql, {"uid": uid, "uid_dashed": str(user_id)}).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        applied = int(r["applied"] or 0)
        callbacks = int(r["callbacks"] or 0)
        sig = r["sig"] or {}
        # SQLite returns JSON as string; Postgres as dict. Normalise.
        if isinstance(sig, str):
            import json as _j
            try:    sig = _j.loads(sig)
            except Exception: sig = {}
        out.append({
            "tailored_resume_id": str(r["tid"]),
            "archetype": (sig or {}).get("archetype", "unknown"),
            "applied":   applied,
            "callbacks": callbacks,
            "response_rate": (callbacks / applied) if applied else 0.0,
        })
    return out


def by_archetype(session: Session, user_id) -> List[Dict[str, Any]]:
    """Roll up across all tailored resumes that share an archetype."""
    rows = by_tailored_resume(session, user_id)
    agg: Dict[str, Dict[str, int]] = {}
    for r in rows:
        a = r["archetype"]
        bucket = agg.setdefault(a, {"applied": 0, "callbacks": 0})
        bucket["applied"]   += r["applied"]
        bucket["callbacks"] += r["callbacks"]
    return [
        {"archetype": a,
         "applied":   v["applied"],
         "callbacks": v["callbacks"],
         "response_rate": (v["callbacks"] / v["applied"]) if v["applied"] else 0.0}
        for a, v in sorted(agg.items())
    ]
