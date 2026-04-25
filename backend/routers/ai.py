"""AI router — resume/cover-letter generation with Gemini + Groq fallback.

Key resolution order (tried until one works):
  1. user's saved Gemini key (encrypted in DB)
  2. settings.system_gemini_key (SYSTEM_GEMINI_KEY env var)
  3. GEMINI_API_KEY env var (legacy fallback)
  4. user's saved Groq key
  5. GROQ_API_KEY env var

Each provider tries multiple models so a single deprecation/quota error doesn't
kill the request. /ai/health reports which providers are reachable.
"""
import os
from typing import Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.config import settings
from backend.dependencies import get_current_user, require_plan
from backend.models.user import User

router = APIRouter()


def _decrypt_safe(blob: Optional[str]) -> Optional[str]:
    if not blob:
        return None
    try:
        from backend.services.crypto_service import decrypt
        return decrypt(blob)
    except Exception:
        return None


def _resolve_keys(user: User) -> Tuple[Optional[str], Optional[str]]:
    """Return (gemini_key, groq_key) from user → settings → env."""
    gemini = (
        _decrypt_safe(getattr(user, "gemini_key_encrypted", None))
        or settings.system_gemini_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("SYSTEM_GEMINI_KEY")
    )
    groq = (
        _decrypt_safe(getattr(user, "groq_key_encrypted", None))
        or os.environ.get("GROQ_API_KEY")
    )
    return gemini, groq


# Models in fallback order. The primary stays gemini-1.5-flash for cost; we add
# 2.0-flash and 1.5-pro as automatic fallbacks for quota / region errors.
_GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
]
# Groq model names change frequently; this list is current as of 2026-04.
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


def _gemini_generate(api_key: str, prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    last_err: Optional[Exception] = None
    for model_name in _GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            text = (getattr(resp, "text", "") or "").strip()
            if text:
                return text
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Gemini models failed: {last_err}")


def _groq_generate(api_key: str, prompt: str) -> str:
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("Groq SDK not installed (pip install groq)")
    client = Groq(api_key=api_key)
    last_err: Optional[Exception] = None
    for model_name in _GROQ_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.7,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Groq models failed: {last_err}")


def _generate(prompt: str, user: User) -> str:
    """Try Gemini first, fall back to Groq. Raise HTTPException if both fail."""
    gemini_key, groq_key = _resolve_keys(user)
    errors = []

    if gemini_key:
        try:
            return _gemini_generate(gemini_key, prompt)
        except Exception as e:
            errors.append(f"gemini: {type(e).__name__}: {str(e)[:200]}")

    if groq_key:
        try:
            return _groq_generate(groq_key, prompt)
        except Exception as e:
            errors.append(f"groq: {type(e).__name__}: {str(e)[:200]}")

    if not gemini_key and not groq_key:
        raise HTTPException(
            status_code=503,
            detail="AI engine not configured. Add a Gemini or Groq API key in Settings → API Keys, or set SYSTEM_GEMINI_KEY on the server.",
        )

    raise HTTPException(
        status_code=502,
        detail=f"All AI providers failed. {' | '.join(errors)}",
    )


@router.get("/health")
async def ai_health(user: User = Depends(get_current_user)):
    """Reports which AI providers are reachable for the current user."""
    gemini_key, groq_key = _resolve_keys(user)
    out = {
        "gemini": {"configured": bool(gemini_key), "ok": False, "error": None},
        "groq": {"configured": bool(groq_key), "ok": False, "error": None},
    }
    if gemini_key:
        try:
            _gemini_generate(gemini_key, "Say OK")
            out["gemini"]["ok"] = True
        except Exception as e:
            out["gemini"]["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    if groq_key:
        try:
            _groq_generate(groq_key, "Say OK")
            out["groq"]["ok"] = True
        except Exception as e:
            out["groq"]["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return out


@router.post("/enhance-summary")
async def enhance_summary(
    text: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
):
    prompt = (
        "Enhance the following professional resume summary. Make it more impactful, "
        "professional, and action-oriented. Highlight achievements and skills. "
        "Return ONLY the enhanced summary text — no quotes, no markdown, no preamble.\n\n"
        f"Original summary:\n{text}"
    )
    return {"text": _generate(prompt, user)}


@router.post("/enhance-bullet")
async def enhance_bullet(
    text: str = Body(..., embed=True),
    title: str = Body("", embed=True),
    company: str = Body("", embed=True),
    user: User = Depends(get_current_user),
):
    context = f" for a {title} role at {company}" if title and company else ""
    prompt = (
        f"Enhance the following resume bullet point{context}. Use the XYZ formula "
        "(Accomplished X as measured by Y, by doing Z) where possible. Start with a "
        "strong action verb. Return ONLY the bullet text — no symbol, quotes, or "
        f"formatting.\n\nOriginal bullet: {text}"
    )
    out = _generate(prompt, user).lstrip("-*•").strip()
    return {"text": out}


@router.post("/generate-bullets")
async def generate_bullets(
    title: str = Body(..., embed=True),
    company: str = Body(..., embed=True),
    count: int = Body(3, embed=True),
    user: User = Depends(get_current_user),
):
    prompt = (
        f"Generate {count} professional resume bullet points for a {title} at {company}. "
        "Action-oriented, impactful, role-specific achievements. Separate by newlines. "
        "No bullet symbols, dashes, quotes, or markdown."
    )
    out = _generate(prompt, user)
    lines = [line.lstrip("-*•").strip() for line in out.split("\n") if line.strip()]
    return {"bullets": lines[:count]}


@router.post("/cover-letter")
async def generate_cover_letter(
    job_description: str = Body(..., embed=True),
    user: User = Depends(require_plan("pro")),
):
    prompt = (
        "You are an expert career coach. Write a compelling, professional cover letter "
        "for the following job description. Personalize, highlight qualifications and "
        "enthusiasm, professional but warm tone, 3-4 paragraphs. DO NOT use placeholder "
        "brackets like [Your Name]. Return ONLY the cover letter text, no preamble or markdown.\n\n"
        f"Job Description:\n{job_description[:3000]}"
    )
    return {"cover_letter": _generate(prompt, user)}


@router.post("/cover-letter/free-preview")
async def cover_letter_preview(
    job_description: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
):
    prompt = (
        "Write a short, 1-paragraph professional cover letter opening for this job. "
        "Return only the opening paragraph, no preamble.\n\n"
        f"Job Description:\n{job_description[:1500]}"
    )
    return {
        "preview": _generate(prompt, user),
        "locked": True,
        "upgrade_message": "Upgrade to Pro to generate full, tailored cover letters for every application.",
    }
