"""Phase D — Tailored resume cache + storage.

The store owns the "build once, reuse forever" lifecycle. A tailored PDF is
indexed by (user_id, jd_hash, profile_version):

  * first call → run jd_analyser → resume_tailor → resume_pdf, write PDF
    to disk, persist a row.
  * subsequent calls with the same key → return the cached row, NO LLM
    calls, NO PDF re-render.

Profile changes bump `profile_version` (set by the caller on the profile
dict via the special `_profile_version` key). That invalidates the cache
automatically so stale tailorings don't get re-used.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.tailored_resume import TailoredResume as TailoredResumeRow
from backend.services import jd_analyser, resume_tailor, resume_pdf
from backend.services.career_schemas import TailoredResume


@dataclass
class StoreEntry:
    id:           uuid.UUID
    user_id:      uuid.UUID
    jd_hash:      str
    profile_ver:  int
    pdf_path:     str
    jd_coverage:  Optional[float]


def _profile_version(profile: Dict[str, Any]) -> int:
    """Derive a cache-busting version from the profile dict.

    Priority:
      1. Explicit `_profile_version` int — callers that manage versions manually.
      2. Hash of resume_hash + key experience/skills content — auto-invalidates
         whenever the user uploads a new resume or edits their profile.
      3. Fall back to 1 so unversioned profiles cache safely.
    """
    v = profile.get("_profile_version")
    if isinstance(v, int):
        return v

    import hashlib, json
    # Build a stable fingerprint from the fields that affect resume output.
    fingerprint_parts = [
        profile.get("resume_hash") or "",
        profile.get("name") or "",
        # Serialize skills + experiences so any edit bumps the version.
        json.dumps(profile.get("skills", []), sort_keys=True),
        json.dumps(profile.get("experiences", []), sort_keys=True),
        json.dumps(profile.get("education", []), sort_keys=True),
    ]
    h = hashlib.sha256("|".join(fingerprint_parts).encode()).hexdigest()
    # Truncate to a positive 32-bit int so it fits in the DB integer column.
    return int(h[:8], 16) % (2 ** 31)


def _to_entry(row: TailoredResumeRow) -> StoreEntry:
    return StoreEntry(
        id=row.id, user_id=row.user_id, jd_hash=row.jd_hash,
        profile_ver=row.profile_ver, pdf_path=row.pdf_path,
        jd_coverage=row.jd_coverage,
    )


def get(session: Session, user_id: uuid.UUID, jd_text: str,
        *, profile_ver: int = 1) -> Optional[StoreEntry]:
    """Lookup by (user_id, jd_hash, profile_ver). Returns None on miss."""
    from backend.services.jd_analyser import _hash_jd
    jd_hash = _hash_jd(jd_text)
    row = session.execute(
        select(TailoredResumeRow).where(
            TailoredResumeRow.user_id == user_id,
            TailoredResumeRow.jd_hash == jd_hash,
            TailoredResumeRow.profile_ver == profile_ver,
        )
    ).scalar_one_or_none()
    if not row:
        return None
    # Refuse to return a cache entry whose PDF was deleted from disk.
    if not os.path.exists(row.pdf_path):
        return None
    return _to_entry(row)


def get_or_build(
    session: Session,
    user_id: uuid.UUID,
    profile: Dict[str, Any],
    jd_text: str,
    *,
    jd_llm: Optional[Callable[..., Optional[str]]] = None,
    tailor_llm: Optional[Callable[..., Optional[str]]] = None,
    upload_dir: str = "uploads/tailored",
    config: Optional[Dict[str, Any]] = None,
) -> StoreEntry:
    """Return a StoreEntry for the (user, JD, profile_ver) tuple, building
    a fresh tailoring + PDF on cache miss. Idempotent: concurrent callers
    on a miss may race, but the UniqueConstraint guarantees only one row wins.
    """
    profile_ver = _profile_version(profile)
    cached = get(session, user_id, jd_text, profile_ver=profile_ver)
    if cached:
        return cached

    # ── Build ──────────────────────────────────────────────────────────────
    jd_sig = jd_analyser.analyse(jd_text, llm=jd_llm, config=config)
    tailored = resume_tailor.tailor(profile, jd_sig, llm=tailor_llm, config=config)

    user_dir = os.path.join(upload_dir, str(user_id))
    pdf_path = os.path.join(user_dir, f"{jd_sig.jd_hash}_v{profile_ver}.pdf")
    resume_pdf.render_to_path(tailored, pdf_path)

    row = TailoredResumeRow(
        id           = uuid.uuid4(),
        user_id      = user_id,
        jd_hash      = jd_sig.jd_hash,
        jd_signature = jd_sig.model_dump(),
        resume_json  = tailored.model_dump(),
        pdf_path     = pdf_path,
        model_used   = None,
        profile_ver  = profile_ver,
        jd_coverage  = tailored.jd_coverage,
    )
    session.add(row)
    try:
        session.commit()
    except Exception:
        # Race lost — another worker just wrote it. Re-read.
        session.rollback()
        cached = get(session, user_id, jd_text, profile_ver=profile_ver)
        if cached:
            return cached
        raise
    return _to_entry(row)
