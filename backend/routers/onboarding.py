"""
Onboarding router — 4-step wizard API.

Step 1: POST /onboarding/resume        — upload + parse + dedup
Step 2: POST /onboarding/preferences   — job prefs
Step 3: POST /onboarding/credentials   — platform passwords (encrypted)
Step 4: POST /onboarding/autofill      — autofill bank + cover letter
GET    /onboarding/status              — which steps are complete
GET    /onboarding/test/{platform}     — validate stored credentials
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm.attributes import flag_modified

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.profile import UserProfile
from backend.services.crypto_service import encrypt_dict
from backend.services.resume_parser import save_and_parse_resume

router = APIRouter()


async def _get_profile(user: User, db: AsyncSession) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(500, "Profile not found")
    return profile


# ── Step 1: Resume Upload ─────────────────────────────────────────────────────
@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)

    gemini_key = None
    if user.gemini_key_encrypted:
        from backend.services.crypto_service import decrypt
        gemini_key = decrypt(user.gemini_key_encrypted)

    resume_url, resume_hash, extracted = await save_and_parse_resume(
        file, user.id, db, gemini_key=gemini_key
    )

    profile.resume_url = resume_url
    profile.resume_hash = resume_hash
    profile.resume_filename = file.filename
    profile.extracted_data = extracted

    # Pre-fill autofill bank from extracted data
    if extracted and not extracted.get("error"):
        bank = dict(profile.autofill_bank or {})  # new dict
        bank.update({
            "full_name": extracted.get("name", bank.get("full_name", "")),
            "email": extracted.get("email", bank.get("email", "")),
            "phone": extracted.get("phone", bank.get("phone", "")),
            "linkedin": extracted.get("linkedin_url", bank.get("linkedin", "")),
            "location": extracted.get("location", bank.get("location", "")),
            "skills": ", ".join(extracted.get("skills", [])),
        })
        profile.autofill_bank = bank
        flag_modified(profile, "autofill_bank")

    await db.commit()
    return {
        "resume_url": resume_url,
        "resume_hash": resume_hash,
        "filename": file.filename,
        "extracted": extracted,
    }


# ── Step 2: Job Preferences ───────────────────────────────────────────────────
class PreferencesRequest(BaseModel):
    # Frontend wizard fields
    job_titles: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    remote: Optional[bool] = None
    employment_types: Optional[List[str]] = None
    # Legacy / extended fields
    keywords: Optional[List[str]] = None
    job_type: Optional[str] = None
    internship_duration: Optional[str] = None
    work_mode: Optional[str] = None
    target_companies: Optional[List[str]] = None
    exclude_companies: Optional[List[str]] = None
    min_stipend: Optional[int] = None
    start_date: Optional[str] = None
    match_threshold: Optional[int] = 60
    # Web-search tab budget — one of 20/50/70/100 from the UI preset selector.
    # Clamped server-side in the applier so a malformed value can't over-open.
    web_search_tab_limit: Optional[int] = None
    web_search_max_queries: Optional[int] = None
    web_search_extra_sites: Optional[List[str]] = None
    google_login_wait_sec: Optional[int] = None
    disable_web_search: Optional[bool] = None


@router.post("/preferences")
async def save_preferences(
    body: PreferencesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    prefs = dict(profile.job_preferences or {})   # always a NEW dict so SQLAlchemy detects the change
    data = body.model_dump(exclude_none=True)
    prefs.update(data)
    profile.job_preferences = prefs
    flag_modified(profile, "job_preferences")      # belt-and-suspenders: mark column dirty
    await db.commit()
    return {"message": "Preferences saved"}


# ── Step 3: Platform Credentials ──────────────────────────────────────────────
class PlatformCred(BaseModel):
    email: str
    password: str


class CredentialsRequest(BaseModel):
    # Frontend sends { platforms: { linkedin: {email, password}, ... } }
    platforms: Optional[Dict[str, PlatformCred]] = None
    # Legacy single-platform form
    platform: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


@router.post("/credentials")
async def save_credentials(
    body: CredentialsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    creds = dict(profile.platform_passwords or {})  # new dict

    if body.platforms:
        for platform, cred in body.platforms.items():
            encrypted = encrypt_dict({
                "email": cred.email,
                "password": cred.password,
            })
            creds[platform] = encrypted
    elif body.platform and body.email and body.password:
        encrypted = encrypt_dict({"email": body.email, "password": body.password})
        creds[body.platform] = encrypted

    profile.platform_passwords = creds
    flag_modified(profile, "platform_passwords")
    await db.commit()
    return {"message": "Credentials saved (encrypted)"}


@router.get("/test/{platform}")
async def test_credentials(
    platform: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate stored credentials. Returns {valid: bool, message: str}."""
    profile = await _get_profile(user, db)
    creds = profile.platform_passwords or {}
    if not creds.get(platform):
        return {"valid": False, "message": "No credentials stored for this platform"}
    return {"valid": True, "message": "Credentials stored (live validation requires browser agent)"}


# ── Step 4: Autofill Bank ─────────────────────────────────────────────────────
class AutofillRequest(BaseModel):
    autofill_bank: Optional[Dict[str, Any]] = None
    fields: Optional[Dict[str, Any]] = None   # frontend sends 'fields'
    cover_letter: Optional[str] = None


@router.post("/autofill")
async def save_autofill(
    body: AutofillRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    bank = body.autofill_bank or body.fields or {}
    if bank:
        existing = dict(profile.autofill_bank or {})  # new dict
        existing.update(bank)
        profile.autofill_bank = existing
        flag_modified(profile, "autofill_bank")
    if body.cover_letter:
        profile.cover_letter = body.cover_letter
    await db.commit()
    return {"message": "Autofill bank saved"}


# ── LinkedIn Session Cookies (bypass CAPTCHA) ────────────────────────────────

class LinkedInCookiesRequest(BaseModel):
    cookies_json: str   # raw JSON exported from browser cookie extension


@router.post("/linkedin-cookies")
async def save_linkedin_cookies(
    body: LinkedInCookiesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Store encrypted LinkedIn session cookies to bypass security challenges.

    Rejects uploads that don't contain a usable session — saves the user from
    discovering this only after the first agent run produces 0 applies.
    """
    import json as _json
    from backend.services.linkedin_cookies import parse_export, has_valid_session, extract_li_at
    # Validate that it's a parseable JSON array
    try:
        parsed = _json.loads(body.cookies_json)
        if not isinstance(parsed, list):
            raise ValueError("Must be a JSON array")
        if len(parsed) == 0:
            raise HTTPException(400, "Cookie list is empty")
    except (_json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(400, f"Invalid cookies JSON: {exc}")

    # The parser also runs Selenium-compat sanitisation; if it returns empty
    # the upload was garbage. If it returns cookies without li_at, the user
    # exported BEFORE logging in — the most common mistake.
    sanitised = parse_export(body.cookies_json)
    if not sanitised:
        raise HTTPException(400, "No valid cookies found after parsing.")
    if not has_valid_session(sanitised):
        raise HTTPException(400,
            "Cookies do not include `li_at` — make sure you exported AFTER "
            "logging in to linkedin.com.")

    from backend.services.crypto_service import encrypt
    profile = await _get_profile(user, db)
    creds = dict(profile.platform_passwords or {})
    creds["linkedin_cookies"] = encrypt(body.cookies_json)
    profile.platform_passwords = creds
    flag_modified(profile, "platform_passwords")
    await db.commit()
    return {"message": f"Saved {len(parsed)} LinkedIn cookies (encrypted).", "count": len(parsed)}


@router.get("/linkedin-cookies-status")
async def linkedin_cookies_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rich status — does the user have cookies stored AND do they include
    a valid `li_at`? Surfaces the most common failure (exported BEFORE
    logging in) before the agent run wastes time on it."""
    from backend.services.crypto_service import decrypt
    from backend.services.linkedin_cookies import parse_export, extract_li_at
    profile = await _get_profile(user, db)
    creds = profile.platform_passwords or {}
    blob = creds.get("linkedin_cookies")
    if not blob:
        return {"stored": False, "has_li_at": False, "count": 0, "ready": False}
    try:
        raw = decrypt(blob)
    except Exception:
        return {"stored": True, "has_li_at": False, "count": 0, "ready": False,
                "error": "Could not decrypt stored cookies — please re-upload."}
    cookies = parse_export(raw)
    li_at = extract_li_at(cookies)
    # Estimate session expiry from li_at's `expiry` field if available.
    expiry_unix = None
    for c in cookies:
        if c.get("name") == "li_at" and isinstance(c.get("expiry"), int):
            expiry_unix = c["expiry"]
            break
    return {
        "stored":     True,
        "count":      len(cookies),
        "has_li_at":  bool(li_at),
        "expiry":     expiry_unix,
        "ready":      bool(li_at),
    }


@router.delete("/linkedin-cookies")
async def delete_linkedin_cookies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    creds = dict(profile.platform_passwords or {})
    creds.pop("linkedin_cookies", None)
    profile.platform_passwords = creds
    flag_modified(profile, "platform_passwords")
    await db.commit()
    return {"message": "LinkedIn cookies removed."}


# ── Credentials Status (which platforms have creds stored) ───────────────────
@router.get("/credentials-status")
async def credentials_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    creds = profile.platform_passwords or {}
    return {
        platform: platform in creds
        for platform in ["linkedin", "wellfound", "internshala", "unstop", "naukri"]
    }


# ── Status ────────────────────────────────────────────────────────────────────
@router.get("/status")
async def onboarding_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_profile(user, db)
    steps = {
        1: bool(profile.resume_url),
        2: bool(profile.job_preferences),
        3: bool(profile.platform_passwords),
        4: bool(profile.autofill_bank),
    }
    return {
        "steps": steps,
        "complete": all(steps.values()),
        "current_step": next((k for k, v in steps.items() if not v), 5),
    }

# ── Credentials (emails only for UI) ──────────────────────────────────────────
@router.get("/credentials")
async def get_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns stored credential emails (passwords excluded for security)."""
    profile = await _get_profile(user, db)
    from backend.services.crypto_service import decrypt_dict
    
    res = {}
    creds = profile.platform_passwords or {}
    for platform, encrypted in creds.items():
        try:
            decrypted = decrypt_dict(encrypted)
            res[platform] = decrypted.get("email", "")
        except:
            res[platform] = ""
    return res
