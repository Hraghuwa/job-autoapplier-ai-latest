"""Phase E — Resume path resolver.

The single entry point appliers use to decide which PDF to upload for a job:

    path = resolve_resume_path(config, jd_text=jd_text)
    driver.find_element(...).send_keys(path)

Behaviour:
  * If we have enough context (user_id, profile, session factory) AND a
    JD text → build/cache a tailored PDF via tailored_resume_store and
    return its path.
  * Otherwise → return config['resume_path'] (the static fallback).
  * NEVER raises. The apply pipeline must never crash because tailoring
    failed; a static upload is always better than no upload.

The caller (each `*_applier.py`) provides these keys on the config dict:
    user_id            uuid.UUID
    resume_path        str       — static fallback PDF on disk
    profile            dict      — at minimum {name,email,experience}
    _session_factory   callable  — sessionmaker, lets us open a sync session
    _tailored_upload_dir str     — directory to write tailored PDFs into
    _jd_llm / _tailor_llm        — optional, tests inject fakes
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def resolve_resume_path(config: Dict[str, Any], *, jd_text: Optional[str] = None) -> str:
    """Return the path to upload. Tailored PDF on success, static on any
    failure. Never raises."""
    static = config.get("resume_path") or ""
    user_id = config.get("user_id")
    profile = config.get("profile") or {}
    session_factory = config.get("_session_factory")
    upload_dir = config.get("_tailored_upload_dir") or "uploads/tailored"

    if not jd_text or not user_id or not profile or session_factory is None:
        return static

    if isinstance(user_id, str):
        import uuid
        try:
            user_id = uuid.UUID(user_id)
        except ValueError:
            return static

    try:
        from backend.services import tailored_resume_store
        with session_factory() as session:
            entry = tailored_resume_store.get_or_build(
                session, user_id, profile, jd_text,
                jd_llm=config.get("_jd_llm"),
                tailor_llm=config.get("_tailor_llm"),
                upload_dir=upload_dir,
                config=config,
            )
        return entry.pdf_path
    except Exception as e:
        log.warning("resume_resolver: tailoring failed (%s) — falling back to static.", e)
        return static
