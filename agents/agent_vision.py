"""
👁️ Agent Vision — Gemini Multimodal Vision for Browser Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses Gemini's vision capabilities to:
  1. See the browser page (screenshot → Gemini)
  2. Detect Apply buttons, form fields, and navigation
  3. Read and understand job descriptions from images
  4. Decide what to click, fill, or skip

This gives the agents "eyes" to handle dynamic/unknown page layouts.
"""

import os
import time
import base64
import tempfile
from io import BytesIO

# Lazy imports
_client = None


def _get_client(config):
    """Get or create the Gemini client."""
    global _client
    if _client is not None:
        return _client

    api_key = config.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    try:
        from google import genai
        _client = genai.Client(api_key=api_key)
        print("  👁️ Agent Vision enabled (Gemini multimodal)")
        return _client
    except Exception as e:
        print(f"  ⚠️ Vision init error: {e}")
        return None


def take_screenshot(driver):
    """Take a screenshot of the current browser page, return as bytes."""
    try:
        return driver.get_screenshot_as_png()
    except Exception:
        return None


def _call_vision(client, prompt, image_bytes, model="gemini-2.0-flash"):
    """Send image + prompt to Gemini vision model with retry."""
    for attempt in range(2):
        try:
            from google.genai import types

            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                            types.Part.from_text(text=prompt),
                        ],
                    )
                ],
            )
            return response.text.strip()
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource_exhausted" in err_str:
                if attempt == 0:
                    time.sleep(15)
                    continue
            return None
    return None


# ─────────────────────────────────────────────
#  VISION FUNCTIONS
# ─────────────────────────────────────────────

def see_page(driver, config, question="What do you see on this page?"):
    """
    Take a screenshot and ask Gemini to analyze the page.
    Returns the AI's text response, or None if vision unavailable.
    """
    client = _get_client(config)
    if not client:
        return None

    screenshot = take_screenshot(driver)
    if not screenshot:
        return None

    return _call_vision(client, question, screenshot)


def find_apply_button(driver, config):
    """
    Use vision to find the Apply button on a job page.
    Returns a description of where the button is, or None.
    """
    client = _get_client(config)
    if not client:
        return None

    screenshot = take_screenshot(driver)
    if not screenshot:
        return None

    prompt = """Look at this job page screenshot. I need to find the "Apply" or "Apply Now" button.

Answer in this EXACT format (one line only):
FOUND: [button text] at [location description]
or
NOTFOUND: [reason]

Be specific about the button's location (top-right, center, bottom, etc.)."""

    result = _call_vision(client, prompt, screenshot)
    if result and result.startswith("FOUND:"):
        return result
    return None


def analyze_form(driver, config):
    """
    Use vision to analyze the current form on the page.
    Returns a list of form fields detected with suggested values.
    """
    client = _get_client(config)
    if not client:
        return None

    screenshot = take_screenshot(driver)
    if not screenshot:
        return None

    # Build the profile summary DYNAMICALLY from the logged-in user's config.
    # Nothing here is hardcoded — if a field is missing, we skip it.
    profile = config.get("profile", {}) or {}
    email = config.get("email") or profile.get("email") or ""

    profile_lines = []
    def _add(label, val):
        if val:
            profile_lines.append(f"- {label}: {val}")

    _add("Name", profile.get("full_name") or config.get("name"))
    _add("Email", email)
    _add("Phone", profile.get("phone") or profile.get("phone_number"))
    _add("College / Degree",
         " ".join(filter(None, [profile.get("degree") or profile.get("course"),
                                 "at" if (profile.get("college") or profile.get("university")) else None,
                                 profile.get("college") or profile.get("university")])))
    _add("Current role", profile.get("current_role") or profile.get("current_title"))
    _add("Current company", profile.get("current_company"))
    _add("Years of experience", profile.get("years_experience") or profile.get("total_experience"))
    _add("Skills", profile.get("skills") or profile.get("tech_stack"))
    _add("LinkedIn", profile.get("linkedin") or profile.get("linkedin_url"))
    _add("Portfolio", profile.get("personal_website") or profile.get("portfolio"))
    _add("Location", profile.get("location") or profile.get("city"))
    _add("Notice period", profile.get("notice_period"))
    _add("Availability", profile.get("join_date") or profile.get("availability"))
    _add("Bio / Summary", profile.get("bio") or profile.get("about_me"))

    cand_name = profile.get("full_name") or config.get("name") or "the candidate"
    profile_block = "\n".join(profile_lines) if profile_lines else "(profile is sparse — infer reasonable defaults only if required)"

    prompt = f"""Analyze this job application form screenshot for {cand_name}.

Candidate profile:
{profile_block}

List EACH visible form field with the value to fill, in this format:
FIELD: [label] → [value to enter]

For example:
FIELD: Full Name → {cand_name}
FIELD: Email → {email or '<user email>'}
FIELD: Why are you interested? → (use candidate's own voice based on their role and experience above)

Rules:
- ONLY fill fields using data present in the candidate profile above.
- If a field has no matching profile data, output: FIELD: [label] → SKIP
- Never invent personal details (employer names, colleges, email, phone) that are not in the profile.
- If a field is already filled, mark it as FILLED.

List ALL fields you can see."""

    return _call_vision(client, prompt, screenshot)


def read_job_description(driver, config):
    """
    Use vision to read and extract the job description from the current page.
    Returns extracted JD text.
    """
    client = _get_client(config)
    if not client:
        return None

    screenshot = take_screenshot(driver)
    if not screenshot:
        return None

    prompt = """Read this job listing page screenshot. Extract the key information:

1. Job Title:
2. Company Name:
3. Location:
4. Job Type (Intern/Full-time):
5. Key Responsibilities (bullet points):
6. Required Skills:
7. Qualifications:

Extract ONLY what's visible on the page. Be concise."""

    return _call_vision(client, prompt, screenshot)


def decide_action(driver, config, context=""):
    """
    Use vision to decide what action to take next on the current page.
    Returns one of: APPLY, FILL_FORM, NEXT_STEP, SUBMIT, SKIP, SCROLL
    """
    client = _get_client(config)
    if not client:
        return None

    screenshot = take_screenshot(driver)
    if not screenshot:
        return None

    prompt = f"""Look at this browser page screenshot. I'm automating job applications.
Context: {context}

What should I do next? Choose ONE action:
- APPLY: Click the Apply/Apply Now button
- FILL_FORM: There's a form to fill out
- NEXT_STEP: Click Next/Continue button on a multi-step form
- SUBMIT: Click Submit button to complete application
- CLOSE_POPUP: Close a popup/modal/overlay
- SCROLL: Need to scroll down to see more content
- SKIP: This page is not relevant for job application
- LOGIN_REQUIRED: Need to login first
- ALREADY_APPLIED: Already applied to this job

Answer format (one line):
ACTION: [action] | REASON: [brief reason]"""

    result = _call_vision(client, prompt, screenshot)
    if result and "ACTION:" in result:
        action = result.split("ACTION:")[1].split("|")[0].strip()
        return action
    return None


def is_relevant_job(driver, config):
    """
    Use vision to check if the current page shows a job relevant to the user's interests.
    Returns True/False.
    """
    client = _get_client(config)
    if not client:
        return True  # Default to True if vision unavailable

    screenshot = take_screenshot(driver)
    if not screenshot:
        return True

    keywords = config.get("keywords", [])
    kw_list = ", ".join(keywords[:10])

    prompt = f"""Look at this page. Is this a job posting for any of these roles?
{kw_list}

Answer ONLY: YES or NO
(YES if it's related to product management, business development, strategy, consulting, AI, project management, or management roles)"""

    result = _call_vision(client, prompt, screenshot)
    if result:
        return result.strip().upper().startswith("YES")
    return True


def find_and_describe_elements(driver, config, element_type="buttons"):
    """
    Use vision to find and describe interactive elements on the page.
    element_type: 'buttons', 'links', 'inputs', 'dropdowns'
    """
    client = _get_client(config)
    if not client:
        return None

    screenshot = take_screenshot(driver)
    if not screenshot:
        return None

    prompt = f"""Look at this page screenshot and list all visible {element_type}.
For each one, provide:
- Text/Label
- Location (top/middle/bottom, left/center/right)
- Purpose (what it likely does)

Format each as: [{element_type.upper()}] "text" at location — purpose

List the most important ones first."""

    return _call_vision(client, prompt, screenshot)
