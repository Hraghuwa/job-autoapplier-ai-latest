"""Gemini AI service — resume parsing, match scoring, cover letter, interview prep.

Text-generation paths (score_match / cover letter / interview prep) now route
through `llm_router` so they can prefer a local Ollama model and fall back to
Gemini. Resume *parsing* still uses Gemini directly because it needs PDF upload
support that Ollama doesn't expose.
"""
from typing import Optional, Dict, Any, List
import json
import sys
import os

from backend.config import settings

# Ensure repo root is on sys.path so we can import the top-level llm_router
# from inside this backend package.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _get_client(user_key: Optional[str] = None):
    import google.generativeai as genai
    key = user_key or settings.system_gemini_key
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-1.5-flash")


def _friendly_gemini_error(exc: Exception) -> str:
    raw = str(exc)
    lower = raw.lower()
    if "api_key_invalid" in lower or "api key not valid" in lower or "api key expired" in lower:
        return "Resume uploaded, but AI parsing was skipped because the Gemini API key is invalid or expired."
    if "quota" in lower or "rate limit" in lower or "429" in lower:
        return "Resume uploaded, but AI parsing was skipped because the AI provider quota or rate limit was reached."
    if "permission" in lower or "403" in lower:
        return "Resume uploaded, but AI parsing was skipped because the AI provider rejected access."
    return f"Resume uploaded, but AI parsing was skipped: {type(exc).__name__}."


def _call(prompt: str, user_key: Optional[str] = None, role: str = "writer") -> str:
    """Route through llm_router (Ollama → Gemini). Returns '__ERROR__:...' on full failure."""
    try:
        from llm_router import generate
        key = user_key or settings.system_gemini_key
        cfg = {"gemini_api_key": key} if key else {}
        out = generate(prompt, role=role, config=cfg)
        if out:
            return out.strip()
        return "__ERROR__:no provider returned a response"
    except Exception as e:
        return f"__ERROR__:{e}"


def parse_resume(pdf_bytes: bytes, user_key: Optional[str] = None) -> Dict[str, Any]:
    """Extract structured data from resume PDF bytes."""
    import google.generativeai as genai
    key = user_key or settings.system_gemini_key
    genai.configure(api_key=key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = """Extract the following fields from this resume and return ONLY valid JSON.
Fields: name, email, phone, linkedin_url, location, skills (array),
education (array of {degree, institution, year, cgpa}),
experience (array of {company, role, duration, description}),
certifications (array), summary (2 sentences max).
Return only the JSON object, no markdown."""

    try:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name

        uploaded = genai.upload_file(tmp, mime_type="application/pdf")
        response = model.generate_content([prompt, uploaded])
        os.unlink(tmp)

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        return {"error": _friendly_gemini_error(e), "name": "", "email": "", "phone": "", "skills": []}


def score_match(resume_summary: str, jd_text: str, user_key: Optional[str] = None) -> Dict[str, Any]:
    """Score job relevance 0-100."""
    prompt = f"""Given this candidate resume summary and job description, score relevance 0-100.
Return ONLY valid JSON with: score (int), reason (string), matched_skills (array), missing_skills (array).

Resume: {resume_summary[:2000]}
Job Description: {jd_text[:2000]}

JSON only, no markdown."""

    result = _call(prompt, user_key)
    try:
        if result.startswith("__ERROR__"):
            return {"score": 0, "reason": result, "matched_skills": [], "missing_skills": []}
        text = result
        if "```" in text:
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)
    except Exception:
        return {"score": 50, "reason": "Could not parse score", "matched_skills": [], "missing_skills": []}


def generate_cover_letter(resume_summary: str, jd_text: str, user_key: Optional[str] = None) -> str:
    """Generate a 150-word tailored cover letter."""
    prompt = f"""Write a concise 150-word cover letter for this candidate applying to this job.
Candidate summary: {resume_summary[:1500]}
Job description: {jd_text[:1500]}
Tone: professional but enthusiastic.
Do not use generic phrases like 'I am writing to express my interest'.
Output plain text only, no markdown, no subject line."""
    result = _call(prompt, user_key)
    return result if not result.startswith("__ERROR__") else ""


def generate_interview_prep(resume_summary: str, jd_text: str, company: str,
                             n_questions: int = 10,
                             user_key: Optional[str] = None) -> Dict[str, Any]:
    """Generate interview questions + answers + company brief."""
    prompt = f"""Generate interview preparation for this candidate applying to {company}.
Candidate: {resume_summary[:1500]}
Job: {jd_text[:1500]}

Return ONLY valid JSON with:
- questions: array of {{"question": string, "model_answer": string}} ({n_questions} items)
- company_brief: string (2 paragraphs about {company})
- red_flags: array of strings (things to watch for in this role)

JSON only, no markdown."""

    result = _call(prompt, user_key)
    try:
        if "```" in result:
            result = result.split("```")[1].lstrip("json").strip()
        data = json.loads(result)
        data["questions"] = data.get("questions", [])[:n_questions]
        return data
    except Exception:
        return {"questions": [], "company_brief": "", "red_flags": []}
