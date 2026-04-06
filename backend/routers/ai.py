import os
from fastapi import APIRouter, Depends, HTTPException, Body
from backend.dependencies import get_current_user, require_plan
from backend.models.user import User
import google.generativeai as genai
from backend.config import settings

router = APIRouter()

# Configure Gemini
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

@router.post("/enhance-summary")
async def enhance_summary(
    text: str = Body(..., embed=True),
    user: User = Depends(get_current_user)
):
    if not api_key:
        raise HTTPException(status_code=503, detail="AI engine not configured.")
        
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Enhance the following professional resume summary. Make it more impactful, professional, and action-oriented. 
        It should highlight achievements and skills clearly. Only return the enhanced summary text without any surrounding quotes, Markdown formatting, or preamble.
        
        Original summary:
        {text}
        """
        response = model.generate_content(prompt)
        enhanced_text = response.text.strip()
        return {"text": enhanced_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/enhance-bullet")
async def enhance_bullet(
    text: str = Body(..., embed=True),
    title: str = Body("", embed=True),
    company: str = Body("", embed=True),
    user: User = Depends(get_current_user)
):
    if not api_key:
        raise HTTPException(status_code=503, detail="AI engine not configured.")
        
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        context = f" for a {title} role at {company}" if title and company else ""
        prompt = f"""
        Enhance the following resume bullet point{context}. Use the XYZ formula (Accomplished X as measured by Y, by doing Z) where possible. Make it start with a strong action verb, and sound highly professional. 
        Only return the enhanced bullet point text without bullet symbol, quotes, or formatting.
        
        Original bullet: {text}
        """
        response = model.generate_content(prompt)
        enhanced_text = response.text.strip().lstrip('-').strip()
        return {"text": enhanced_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-bullets")
async def generate_bullets(
    title: str = Body(..., embed=True),
    company: str = Body(..., embed=True),
    count: int = Body(3, embed=True),
    user: User = Depends(get_current_user)
):
    if not api_key:
        raise HTTPException(status_code=503, detail="AI engine not configured.")
        
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Generate {count} professional resume bullet points for a {title} at {company}.
        The bullets should be impactful, action-oriented, and highlight common impressive achievements for this role.
        Separate each bullet point by a newline. Do not include bullet symbols, dashes, quotes or markdown formatting.
        """
        response = model.generate_content(prompt)
        lines = [line.lstrip('-*•').strip() for line in response.text.split('\n') if line.strip()]
        return {"bullets": lines[:count]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cover-letter")
async def generate_cover_letter(
    job_description: str = Body(..., embed=True),
    user: User = Depends(require_plan("pro")),
):
    if not api_key:
        raise HTTPException(status_code=503, detail="AI engine not configured.")

    try:
        from sqlalchemy.ext.asyncio import AsyncSession
        from backend.database import get_db as _gdb
        # Fetch user profile for resume context
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        You are an expert career coach. Write a compelling, professional cover letter 
        for the following job description. The letter should:
        1. Be personalized and specific to the role
        2. Highlight relevant qualifications and enthusiasm
        3. Use a professional but warm tone
        4. Be 3-4 paragraphs long
        5. DO NOT include any placeholder brackets like [Your Name] — write it as a template ready to customize
        6. Return ONLY the cover letter text, no preamble or markdown formatting.

        Job Description:
        {job_description[:3000]}
        """
        response = model.generate_content(prompt)
        cover_letter = response.text.strip()
        return {"cover_letter": cover_letter}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cover-letter/free-preview")
async def cover_letter_preview(
    job_description: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
):
    """Free users get a truncated preview to encourage upgrade."""
    if not api_key:
        raise HTTPException(status_code=503, detail="AI engine not configured.")

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        Write a short, 1-paragraph professional cover letter opening for this job.
        Only return the opening paragraph, no preamble.

        Job Description:
        {job_description[:1500]}
        """
        response = model.generate_content(prompt)
        preview = response.text.strip()
        return {
            "preview": preview,
            "locked": True,
            "upgrade_message": "Upgrade to Pro to generate full, tailored cover letters for every application.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
