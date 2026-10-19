"""After the application goes out: follow-ups, skill gaps, outcomes from email.

Pure functions over plain dicts (one per Application row) so they test without
a DB; the career_ops router does the I/O. fetch_gmail() is the only network code.
"""
from __future__ import annotations

import email
import imaplib
import re
from collections import Counter
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional

# Days of silence before a follow-up is due, per status (followup.md cadence).
CADENCE_DAYS = {"applied": 7, "viewed": 3, "shortlisted": 3, "interview": 1}
MAX_FOLLOWUPS = 2  # per application; more than that reads as pestering
FOLLOWUP_EVENT = "followup_draft"


def _ts(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _status(app: Dict[str, Any]) -> str:
    s = app.get("status")
    return str(getattr(s, "value", s) or "applied")


def followups_due(apps: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Applications that have gone quiet past their cadence, oldest silence first."""
    now = now or datetime.utcnow()
    due = []
    for a in apps:
        status = _status(a)
        cadence = CADENCE_DAYS.get(status)
        if cadence is None:  # offer / rejected — nothing to chase
            continue
        history = a.get("history") or []
        sent = sum(1 for h in history if isinstance(h, dict) and h.get("type") == FOLLOWUP_EVENT)
        if sent >= MAX_FOLLOWUPS:
            continue
        stamps = [_ts(a.get("applied_at"))] + [_ts(h.get("timestamp")) for h in history if isinstance(h, dict)]
        stamps = [t for t in stamps if t]
        if not stamps:
            continue
        quiet = (now - max(stamps)).days
        if quiet >= cadence:
            due.append({"application_id": str(a.get("id")), "company": a.get("company"),
                        "role": a.get("job_title"), "status": status,
                        "days_quiet": quiet, "followups_sent": sent})
    return sorted(due, key=lambda d: -d["days_quiet"])


def skill_gaps(apps: Iterable[Dict[str, Any]], top: int = 10) -> List[Dict[str, Any]]:
    """Most-requested skills the user lacks, counted across their applications.
    Interviews/offers weigh double: those are the roles that wanted them."""
    counts: Counter = Counter()
    label: Dict[str, str] = {}
    for a in apps:
        weight = 2 if _status(a) in ("interview", "offer") else 1
        for s in a.get("missing_skills") or []:
            key = " ".join(str(s).lower().split())
            if key:
                counts[key] += weight
                label.setdefault(key, str(s).strip())
    return [{"skill": label[k], "weight": n} for k, n in counts.most_common(top)]


# ── Outcomes from email ──────────────────────────────────────────────────────
# Order matters: a rejection mentioning "interview" is still a rejection.
_RULES = [
    ("rejected", r"unfortunately|not (to )?(be )?mov(e|ing) forward|decided to (go|move|proceed) "
                 r"(forward )?with (other|another)|position has been filled|not selected|"
                 r"won'?t be (moving|proceeding)|regret to inform"),
    ("offer", r"offer letter|pleased to (extend|offer)|job offer|we'?d like to offer you"),
    ("interview", r"interview|schedule (a|some) time|calendly\.com|availability for a (call|chat)"),
    ("shortlisted", r"assessment|assignment|coding (test|challenge)|hackerrank|codility|"
                    r"shortlisted|next (round|step)"),
    ("viewed", r"(application|profile) (was )?viewed|viewed your application"),
]
_RANK = {"applied": 0, "viewed": 1, "shortlisted": 2, "interview": 3, "offer": 4}


def classify_email(subject: str, body: str) -> Optional[str]:
    text = f"{subject}\n{body}".lower()
    for status, pattern in _RULES:
        if re.search(pattern, text):
            return status
    return None


def _company_key(name: str) -> str:
    name = re.sub(r"\b(inc|llc|ltd|pvt|private|limited|technologies|labs|corp)\b\.?", "", (name or "").lower())
    return re.sub(r"[^a-z0-9]", "", name)


def propose_outcomes(emails: Iterable[Dict[str, Any]], apps: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map emails to status changes for the user to approve — never applied here.
    Only one proposal per application (latest email wins), never a downgrade
    except to 'rejected', and never auto-accepting an offer."""
    apps = list(apps)
    keyed = [(a, _company_key(a.get("company", ""))) for a in apps]
    best: Dict[str, Dict[str, Any]] = {}
    for m in emails:
        status = classify_email(m.get("subject", ""), m.get("body", ""))
        if not status:
            continue
        haystack = re.sub(r"[^a-z0-9]", "", f"{m.get('from', '')} {m.get('subject', '')} {m.get('body', '')[:2000]}".lower())
        matches = [a for a, k in keyed if len(k) >= 3 and k in haystack]
        if len(matches) != 1:  # unmatched or ambiguous → leave it for the user
            continue
        app = matches[0]
        current = _status(app)
        if status == current or (status != "rejected" and _RANK.get(status, 0) <= _RANK.get(current, 0)):
            continue
        aid = str(app.get("id"))
        prev = best.get(aid)
        if prev and (_ts(prev["evidence"]["date"]) or datetime.min) > (_ts(m.get("date")) or datetime.min):
            continue
        best[aid] = {"application_id": aid, "company": app.get("company"), "role": app.get("job_title"),
                     "current_status": current, "proposed_status": status,
                     "evidence": {"from": m.get("from", ""), "subject": m.get("subject", ""),
                                  "date": str(m.get("date") or "")}}
    return list(best.values())


def _decode(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return str(value or "")


def _plain_body(msg) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/plain" and not part.get_filename():
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


def fetch_gmail(address: str, app_password: str, days: int = 30, limit: int = 300) -> List[Dict[str, Any]]:
    """Read recent inbox mail over IMAP with a Gmail app password, read-only.
    The password is used for this call only and never stored."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%d-%b-%Y")
    out: List[Dict[str, Any]] = []
    with imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30) as imap:
        imap.login(address, app_password)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, f'(SINCE "{since}")')
        for num in (data[0].split() if data and data[0] else [])[-limit:]:
            _, msg_data = imap.fetch(num, "(BODY.PEEK[])")  # PEEK: don't mark as read
            if not msg_data or not isinstance(msg_data[0], tuple):
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            try:
                date = parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None).isoformat()
            except Exception:
                date = ""
            out.append({"from": parseaddr(_decode(msg.get("From")))[1] or _decode(msg.get("From")),
                        "subject": _decode(msg.get("Subject")), "body": _plain_body(msg)[:5000],
                        "date": date})
    return out
