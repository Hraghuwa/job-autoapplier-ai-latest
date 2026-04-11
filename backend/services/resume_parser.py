"""Resume upload, SHA-256 dedup, Gemini parsing."""
from typing import Optional, Tuple
import hashlib
import os
import uuid

from fastapi import UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.profile import UserProfile

UPLOAD_DIR = os.path.abspath("uploads")
ALLOWED_MIME = {"application/pdf", "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


async def save_and_parse_resume(
    file: UploadFile,
    user_id: uuid.UUID,
    db: AsyncSession,
    gemini_key: Optional[str] = None,
) -> Tuple[str, str, dict]:
    """
    Save resume file, check SHA-256 dedup, parse with Gemini.
    Returns (resume_url, resume_hash, extracted_data).
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Use PDF or DOCX.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, "File too large. Max 10MB.")

    file_hash = hashlib.sha256(content).hexdigest()

    # Dedup check — same hash for a DIFFERENT user → block
    result = await db.execute(
        select(UserProfile).where(
            UserProfile.resume_hash == file_hash,
            UserProfile.user_id != user_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(409, detail="This resume is already registered to another account.")

    # Save file
    user_dir = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    ext = ".pdf" if "pdf" in (file.content_type or "") else ".docx"
    file_path = os.path.join(user_dir, f"resume{ext}")
    with open(file_path, "wb") as f:
        f.write(content)

    resume_url = file_path  # local path; swap to S3 URL in prod

    # Parse with Gemini (PDF only; DOCX parsing skipped for now)
    extracted = {}
    if ext == ".pdf":
        try:
            from backend.services.gemini_service import parse_resume
            extracted = parse_resume(content, user_key=gemini_key)
        except Exception:
            extracted = {}

    return resume_url, file_hash, extracted
