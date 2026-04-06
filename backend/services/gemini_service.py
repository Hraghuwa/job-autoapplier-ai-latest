"""Gemini AI service — resume parsing, match scoring, cover letter, interview prep."""
from typing import Optional, Dict, Any, List
import json

from backend.config import settings


def _get_client(user_key: Optional[str] = None):
    import google.generativeai as genai
    key = user_key or settings.system_gemini_key
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-1.5-flash")


def _call(prompt: str, user_key: Optional[str] = None) -> str:
    try:
        model = _get_client(user_key)
        response = model.generate_content(prompt)
        return response.text.strip()
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
        return {"error": str(e), "name": "", "email": "", "phone": "", "skills": []}


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
