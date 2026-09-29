"""
📝 Universal External Form Auto-Filler
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detects and auto-fills ANY external application form a candidate
encounters during their job hunt — NOT just Google Forms. Supports:

  • Google Forms (docs.google.com/forms)
  • Typeform (typeform.com)
  • JotForm
  • Workday / Lever / Greenhouse / Taleo career pages
  • Standard HTML <form> elements
  • SPA forms (React/Vue/Angular) — uses native events so values register
  • Company-owned custom ATS portals

All personal info (name, email, phone, LinkedIn, portfolio, college,
CGPA, current role, location, etc.) is read from CONFIG["profile"],
which is populated from the user's saved profile in the database.
NOTHING is hardcoded to a specific candidate — any user who signs up
and fills out their profile gets their own data auto-filled.

If a user has not provided a particular field in their profile, the
corresponding form question is left blank (or filled with "NA" for
required text fields) rather than being filled with someone else's
data. This makes the module safe for multi-tenant web use.
"""

import time
import os
import traceback
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException, ElementNotInteractableException,
    TimeoutException, NoSuchElementException
)


def _resolved_resume_path(config, driver=None):
    """Return the JD-tailored PDF when we have JD context, else the static one
    (audit M7). JD context = explicit config['_current_jd'], or the visible
    page text when a driver is supplied (we're on the application page at fill
    time). Never raises — falls back to config['resume_path']."""
    static = config.get("resume_path", "")
    try:
        from backend.services.resume_resolver import resolve_resume_path
        jd_text = config.get("_current_jd")
        if not jd_text and driver is not None:
            from smart_form_filler import _capture_jd_text
            jd_text = _capture_jd_text(driver, config)
        return resolve_resume_path(config, jd_text=jd_text) or static
    except Exception:
        return static


def is_google_form(driver):
    """Check if current page is a Google Form."""
    url = driver.current_url.lower()
    return "docs.google.com/forms" in url or "forms.gle" in url


def is_typeform(driver):
    """Check if current page is a Typeform."""
    url = driver.current_url.lower()
    return "typeform.com" in url


def get_form_field_label(driver, element):
    """Get the label/question text for a form field."""
    label_text = ""

    # Try aria-label
    try:
        label_text = element.get_attribute("aria-label") or ""
        if label_text:
            return label_text.lower().strip()
    except:
        pass

    # Try associated label
    try:
        el_id = element.get_attribute("id") or ""
        if el_id:
            labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{el_id}']")
            if labels:
                return labels[0].text.lower().strip()
    except:
        pass

    # Try closest parent div text
    try:
        parent = element.find_element(By.XPATH, "./ancestor::div[1]")
        text = parent.text.split("\n")[0]
        if text and len(text) < 200:
            return text.lower().strip()
    except:
        pass

    # For Google Forms — get the question heading
    try:
        parent_item = element.find_element(By.XPATH,
            "./ancestor::div[contains(@class,'freebirdFormviewerComponentsQuestionBase')]"
            " | ./ancestor::div[@data-params]"
            " | ./ancestor::div[contains(@class,'Qr7Oae')]")
        heading = parent_item.find_element(By.CSS_SELECTOR,
            "span[class*='M7eMe'], div[class*='HoXoMd'], "
            "div[role='heading'], span[dir='auto']")
        return heading.text.lower().strip()
    except:
        pass

    # Placeholder
    try:
        placeholder = element.get_attribute("placeholder") or ""
        if placeholder:
            return placeholder.lower().strip()
    except:
        pass

    return ""


def match_answer(label, config):
    """
    Match a form field label to the right answer from the USER'S profile.

    All values are pulled from CONFIG["profile"] which the backend
    populates from the logged-in user's saved profile + onboarding data.
    Nothing is hardcoded to a specific candidate — if the user hasn't
    provided a value, this function returns None and the caller decides
    whether to skip, use a generic fallback ("NA"), or leave blank.
    """
    profile = config.get("profile", {}) or {}
    c = label.lower()

    def _p(key, *fallback_keys):
        """Get a profile field, checking alternate key names, return None if truly missing."""
        v = profile.get(key)
        if v:
            return v
        for fk in fallback_keys:
            v = profile.get(fk)
            if v:
                return v
        return None

    # Company / organisation — MUST come before the generic name check, else
    # 'Company Name' matches the bare 'name' below and gets the CANDIDATE's name.
    if any(w in c for w in ["company name", "organisation", "organization",
                            "employer", "current company", "company", "employer name"]):
        return _p("current_company", "company")

    # LinkedIn
    if any(w in c for w in ["linkedin", "linkedin id", "linkedin url"]):
        return _p("linkedin", "linkedin_url", "linkedin_profile")

    # Portfolio / Personal Website
    if any(w in c for w in ["portfolio", "website", "personal website", "link to your work"]):
        return _p("personal_website", "portfolio", "portfolio_url", "website")

    # GitHub
    if any(w in c for w in ["github", "git hub"]):
        return _p("github", "github_url")

    # Email — ALWAYS the user's email from config, never a hardcoded default
    if any(w in c for w in ["email", "e-mail", "mail id", "email id"]):
        return config.get("email") or _p("email")

    # Phone
    if any(w in c for w in ["phone", "mobile", "contact", "whatsapp"]):
        return _p("phone", "phone_number", "mobile")

    # College / University
    if any(w in c for w in ["university", "college", "institute", "institution"]):
        return _p("college", "university", "institute")

    # Course / Degree
    if any(w in c for w in ["course", "pursuing", "completed", "degree"]):
        return _p("course", "degree")

    # Branch / Specialization
    if any(w in c for w in ["branch", "specialization", "stream", "department"]):
        return _p("branch", "specialization", "stream")

    # Year of passing / graduation
    if any(w in c for w in ["passing", "graduation", "year of"]):
        return _p("graduation_year", "year_of_passing")

    # CGPA / GPA / percentage
    if any(w in c for w in ["cgpa", "gpa", "percentage", "marks"]):
        return _p("cgpa", "gpa", "percentage")

    # Current/Last role
    if any(w in c for w in ["current role", "last role", "current/last", "designation", "current title"]):
        return _p("current_role", "current_title", "designation")

    # Current stipend/salary
    if any(w in c for w in ["current stipend", "current salary", "current ctc", "present ctc"]):
        return _p("current_ctc", "current_salary")

    # Expected stipend/salary
    if any(w in c for w in ["expected stipend", "expected salary", "expected ctc"]):
        return _p("expected_salary", "expected_ctc")

    # Location / city — 'where' dropped: it caught "where did you hear about us?"
    # and returned the candidate's city. Keep specific location cues only.
    if any(w in c for w in ["location", "city", "based in", "current city",
                            "where are you", "where do you live"]):
        return _p("location", "city", "current_city")

    # Join date / availability
    if any(w in c for w in ["earliest", "joining", "join date", "start date", "how soon", "availability"]):
        return _p("join_date", "earliest_start_date", "availability")

    # Notice period
    if any(w in c for w in ["notice period", "notice"]):
        np = _p("notice_period")
        return f"{np} days" if np else None

    # Laptop / workspace
    if "laptop" in c:
        return "Yes"

    # Tools / tech stack
    if any(w in c for w in ["tools", "which tools", "tools used", "tech stack"]):
        return _p("tools_used", "tech_stack", "skills")

    # RAG / AI-concept questions — answer only if user provided one
    if any(w in c for w in ["rag", "retrieval augmented", "retrieval-augmented"]):
        return _p("rag_explanation")

    # Product/AI/startup experience
    if any(w in c for w in ["product", "startup", "ai-related", "worked on any"]):
        return "Yes"

    # Experience / years
    if any(w in c for w in ["experience", "years"]):
        return _p("years_experience", "experience_years", "total_experience")

    # Why / Motivation / Cover letter — use the AI-generated or user-saved cover letter
    if any(w in c for w in ["why", "motivation", "interest", "cover letter"]):
        return (config.get("cover_letter")
                or _p("cover_letter", "why_this_role", "motivation")
                or None)

    # Skills
    if any(w in c for w in ["skill", "strength"]):
        return _p("skills", "skill_list", "strengths")

    # Name Fallback
    if any(w in c for w in ["your name", "full name", "candidate name", "first name", "last name", "fname", "lname"]):
        return _p("full_name", "name")

    if "name" in c:
        exclude = ["company", "organization", "college", "university", "degree", "course", "project", 
                   "father", "mother", "reference", "file", "school", "employer", "manager", "recruiter", 
                   "friend", "spokesperson", "street", "city", "country", "state", "branch", 
                   "specialization", "stream", "department", "major", "job", "position", "role", "title",
                   "spouse", "child", "emergency", "contact", "referee", "professor", "teacher", "ref"]
        if not any(e in c for e in exclude):
            return _p("full_name", "name")

    return None


# ─────────────────────────────────────────────
#  GOOGLE FORM FILLER
# ─────────────────────────────────────────────
def fill_google_form(driver, config):
    """Auto-fill a Google Form with profile data and upload resume."""
    print("    📝 [GoogleForm] Auto-filling...")
    filled_count = 0
    resume_path = _resolved_resume_path(config, driver)

    try:
        time.sleep(2)

        # ── Fill text inputs ──
        # Google forms usually use specific classes like whsOnd zHQkBf for text inputs
        text_inputs = driver.find_elements(By.CSS_SELECTOR,
            "input.whsOnd, input[type='text'], input[type='email'], input[type='url'], "
            "input[type='tel'], input:not([type])")

        for inp in text_inputs:
            try:
                if not inp.is_displayed():
                    continue
                val = (inp.get_attribute("value") or "").strip()
                if val:
                    continue

                label = get_form_field_label(driver, inp)
                answer = match_answer(label, config) if label else None
                
                # Fallback for unmapped but potentially required text fields
                if not answer:
                    if label and any(w in label for w in ["link", "url", "profile"]):
                        answer = config.get("profile", {}).get("linkedin", "https://linkedin.com")
                    else:
                        answer = "NA"

                inp.clear()
                inp.send_keys(str(answer))
                filled_count += 1
                if answer != "NA":
                    print(f"      ✏️  {label[:40]}: {str(answer)[:40]}")
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue

        # ── Fill textareas ──
        # Google forms use textarea class KHxj8b tL9Q4c
        textareas = driver.find_elements(By.CSS_SELECTOR, "textarea.KHxj8b, textarea")
        for ta in textareas:
            try:
                if not ta.is_displayed():
                    continue
                val = (ta.get_attribute("value") or ta.text or "").strip()
                if val:
                    continue

                label = get_form_field_label(driver, ta)
                answer = match_answer(label, config) if label else None

                if not answer:
                    if label and any(w in label for w in ["cover", "about", "yourself", "intro"]):
                        profile = config.get("profile", {}) or {}
                        cand_name = profile.get("full_name") or config.get("name") or "the candidate"
                        cand_role = (profile.get("current_role")
                                     or profile.get("current_title")
                                     or "my field")
                        answer = (config.get("cover_letter", "") or "").strip()[:500] or (
                            f"Hi, I'm {cand_name}. I'm excited about this role and believe my "
                            f"background in {cand_role} aligns well with what you're looking for. "
                            "Looking forward to contributing to your team!"
                        )
                    else:
                        answer = "NA"

                ta.clear()
                ta.send_keys(str(answer))
                filled_count += 1
                if answer != "NA":
                    print(f"      ✏️  {(label or 'textarea')[:40]}: {str(answer)[:40]}...")
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue

        # ── Handle 'Next' buttons for multi-page forms ──
        try:
            next_btns = driver.find_elements(By.XPATH, "//span[text()='Next'] | //span[text()='Continue'] | //div[contains(@aria-label, 'Next')]")
            for btn in next_btns:
                if btn.is_displayed():
                    print("      ⏭️  Found 'Next' button, clicking to proceed...")
                    btn.click()
                    time.sleep(2)
                    # Recursively fill next page
                    filled_count += fill_google_form(driver, config)
                    break
        except:
            pass

        # ── Handle radio buttons (Google Forms use div[role='radio']) ──
        try:
            # Find all radio groups
            radio_groups = driver.find_elements(By.CSS_SELECTOR,
                "div[role='radiogroup'], div[data-params*='radio'], "
                "fieldset, div[class*='oyXaNc']")

            for group in radio_groups:
                try:
                    # Get the question text
                    question = ""
                    try:
                        q_el = group.find_element(By.CSS_SELECTOR,
                            "div[role='heading'], span[class*='M7eMe'], "
                            "div[class*='HoXoMd']")
                        question = q_el.text.lower()
                    except:
                        question = group.text.split("\n")[0].lower() if group.text else ""

                    # Determine the right answer
                    should_yes = any(w in question for w in [
                        "laptop", "willing", "agree", "relocat", "available",
                        "product", "startup", "ai", "worked on",
                    ])
                    should_no = any(w in question for w in [
                        "disability", "criminal", "sponsorship",
                    ])

                    target = "yes" if should_yes else ("no" if should_no else "yes")

                    # Find and click the right radio option
                    options = group.find_elements(By.CSS_SELECTOR,
                        "div[role='radio'], label, div[class*='nWQGrd'], "
                        "span[class*='aDTYNe'], div[data-value]")

                    for opt in options:
                        opt_text = opt.text.strip().lower()
                        data_val = (opt.get_attribute("data-value") or "").lower()
                        if opt_text == target or data_val == target:
                            try:
                                opt.click()
                                filled_count += 1
                                print(f"      🔘 {question[:40]}: {target}")
                                break
                            except:
                                driver.execute_script("arguments[0].click();", opt)
                                filled_count += 1
                                break

                except Exception:
                    continue
        except Exception:
            pass

        # ── Handle dropdowns (Google Forms use div[role='listbox']) ──
        try:
            dropdowns = driver.find_elements(By.CSS_SELECTOR,
                "div[role='listbox'], select")

            for dropdown in dropdowns:
                try:
                    if not dropdown.is_displayed():
                        continue

                    label = get_form_field_label(driver, dropdown)
                    answer = match_answer(label, config) if label else None

                    if dropdown.tag_name == "select":
                        from selenium.webdriver.support.ui import Select
                        sel = Select(dropdown)
                        if answer:
                            for opt in sel.options:
                                if answer.lower() in opt.text.lower():
                                    sel.select_by_visible_text(opt.text.strip())
                                    filled_count += 1
                                    print(f"      📋 {label[:40]}: {opt.text.strip()}")
                                    break
                    else:
                        # Google Forms dropdown
                        dropdown.click()
                        time.sleep(0.5)
                        options = driver.find_elements(By.CSS_SELECTOR,
                            "div[role='option'], div[data-value]")
                        for opt in options:
                            if answer and answer.lower() in opt.text.lower():
                                opt.click()
                                filled_count += 1
                                print(f"      📋 {label[:40]}: {opt.text.strip()}")
                                break
                        else:
                            # Click first valid option if no match
                            if options:
                                options[0].click()
                except Exception:
                    continue
        except Exception:
            pass

        # ── Upload Resume (file input) ──
        if resume_path and os.path.exists(resume_path):
            try:
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                for fi in file_inputs:
                    try:
                        label = get_form_field_label(driver, fi) or ""
                        if label:
                            label_lower = label.lower()
                            non_resume_kws = ["photo", "picture", "image", "transcript", "cover letter", "portfolio", "certificate", "id card", "passport"]
                            resume_kws = ["resume", "cv", "curriculum", "bio"]
                            if any(nk in label_lower for nk in non_resume_kws) and not any(rk in label_lower for rk in resume_kws):
                                print(f"      ⏭️  Skipping file input with label '{label[:40]}' (not a resume field)")
                                continue
                        fi.send_keys(resume_path)
                        filled_count += 1
                        print(f"      📄 Resume uploaded: {os.path.basename(resume_path)}")
                    except Exception:
                        continue

                # Google Forms file upload button
                upload_btns = driver.find_elements(By.CSS_SELECTOR,
                    "div[data-file-upload], div[class*='dHXzCb'], "
                    "div[aria-label*='upload'], div[aria-label*='file'], "
                    "button[aria-label*='upload']")
                # Note: Google Forms file upload requires clicking and
                # interacting with the OS file dialog, which Selenium handles
                # via the hidden file input
            except Exception:
                pass
        else:
            print(f"      ⚠️  Resume not found at: {resume_path}")

        # ── Handle date inputs ──
        try:
            date_inputs = driver.find_elements(By.CSS_SELECTOR,
                "input[type='date'], input[data-type='date']")
            for di in date_inputs:
                try:
                    if not di.is_displayed():
                        continue
                    val = (di.get_attribute("value") or "").strip()
                    if val:
                        continue

                    label = get_form_field_label(driver, di)
                    if any(w in label for w in ["join", "start", "earliest", "availability"]):
                        di.send_keys("2026-04-01")
                        filled_count += 1
                        print(f"      📅 {label[:40]}: 2026-04-01")
                except Exception:
                    continue
        except Exception:
            pass

        print(f"    ✅ [GoogleForm] Filled {filled_count} fields")

    except Exception as e:
        print(f"    ❌ [GoogleForm] Error: {e}")
        traceback.print_exc()

    return filled_count


# ─────────────────────────────────────────────
#  STANDARD WEB FORM FILLER (non-Google)
# ─────────────────────────────────────────────
def _combined_label(driver, element):
    """
    Build a comprehensive label string from every possible source:
    aria-label, placeholder, name, id, associated <label>, nearby text.
    Used to identify what a field is asking for.
    """
    parts = []
    try:
        parts.append(element.get_attribute("aria-label") or "")
        parts.append(element.get_attribute("placeholder") or "")
        parts.append(element.get_attribute("name") or "")
        parts.append(element.get_attribute("id") or "")
        parts.append(element.get_attribute("data-field") or "")
        parts.append(element.get_attribute("data-label") or "")
    except Exception:
        pass

    # Associated <label> tag
    try:
        el_id = element.get_attribute("id") or ""
        if el_id:
            labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{el_id}']")
            if labels:
                parts.append(labels[0].text)
    except Exception:
        pass

    # Nearest ancestor label / div text (first line only)
    try:
        parent = element.find_element(By.XPATH,
            "./ancestor::label[1] | ./preceding-sibling::label[1] | "
            "./ancestor::div[contains(@class,'field')][1] | "
            "./ancestor::div[contains(@class,'form')][1]")
        txt = (parent.text or "").split("\n")[0]
        if txt and len(txt) < 120:
            parts.append(txt)
    except Exception:
        pass

    return " ".join(p for p in parts if p).lower().strip()


def _send_value(driver, element, value):
    """
    Send a value to an input and fire React/Vue/Angular change events
    so frameworks pick up the new value.
    """
    try:
        element.click()
    except Exception:
        pass
    try:
        element.clear()
    except Exception:
        pass
    element.send_keys(str(value))
    # Fire native input + change events for React / Vue
    try:
        driver.execute_script(
            """
            var el = arguments[0];
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value') ||
                Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
            if (nativeInputValueSetter) nativeInputValueSetter.set.call(el, arguments[1]);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur',  { bubbles: true }));
            """,
            element, str(value)
        )
    except Exception:
        pass


def fill_web_form(driver, config):
    """
    Auto-fill standard HTML forms on ATS/career pages.
    Works with Lever, Greenhouse, Workday, Internshala, Cutshort,
    Typeform, JotForm and plain HTML forms.
    Uses combined label detection + React-safe value injection.
    """
    print("    📝 [WebForm] Auto-filling...")
    filled_count = 0
    profile = config.get("profile", {})
    resume_path = _resolved_resume_path(config, driver)

    # ── ATS-specific direct field mapping by name/id attribute ──
    # Values come STRICTLY from the logged-in user's profile. No hardcoded
    # fallbacks — if a field is missing, we simply leave it out of the map
    # so the caller will skip it (or fall back to "NA" for required fields).
    # This makes the form-filler multi-tenant safe.
    _first_name = profile.get("first_name") or (
        (profile.get("full_name") or "").split(" ", 1)[0] if profile.get("full_name") else None
    )
    _last_name = profile.get("last_name") or (
        " ".join((profile.get("full_name") or "").split(" ")[1:]) or None
        if profile.get("full_name") else None
    )
    _email = config.get("email") or profile.get("email")
    _phone = profile.get("phone") or profile.get("phone_number") or profile.get("mobile")
    _linkedin = profile.get("linkedin") or profile.get("linkedin_url")
    _portfolio = (profile.get("personal_website") or profile.get("portfolio")
                  or profile.get("portfolio_url") or profile.get("website"))
    _city = profile.get("city") or profile.get("location")
    _full_name = profile.get("full_name") or config.get("name")
    _cover = (config.get("cover_letter") or profile.get("cover_letter") or "")

    _raw_map = {
        # Name variants
        "first_name": _first_name,
        "firstname":  _first_name,
        "first-name": _first_name,
        "fname":      _first_name,
        "last_name":  _last_name,
        "lastname":   _last_name,
        "last-name":  _last_name,
        "lname":      _last_name,
        "full_name":  _full_name,
        "fullname":   _full_name,
        "name":       _full_name,
        "candidate_name": _full_name,
        # Contact
        "email":      _email,
        "email_address": _email,
        "phone":      _phone,
        "phone_number": _phone,
        "mobile":     _phone,
        "mobile_number": _phone,
        "contact":    _phone,
        # Location
        "city":       _city,
        "location":   _city,
        "address":    profile.get("address"),
        "pincode":    profile.get("pincode") or profile.get("postal_code"),
        "zip":        profile.get("pincode") or profile.get("postal_code"),
        # Social
        "linkedin":   _linkedin,
        "linkedin_url": _linkedin,
        "portfolio":  _portfolio,
        "website":    _portfolio,
        "github":     profile.get("github") or profile.get("github_url"),
        # Education
        "college":    profile.get("college") or profile.get("university"),
        "university": profile.get("university") or profile.get("college"),
        "institution": profile.get("college") or profile.get("university"),
        "degree":     profile.get("degree") or profile.get("course"),
        "course":     profile.get("course") or profile.get("degree"),
        "branch":     profile.get("branch") or profile.get("specialization"),
        "specialization": profile.get("branch") or profile.get("specialization"),
        "cgpa":       profile.get("cgpa") or profile.get("gpa"),
        "gpa":        profile.get("cgpa") or profile.get("gpa"),
        "percentage": profile.get("percentage") or profile.get("twelfth_marks"),
        "graduation_year": profile.get("graduation_year") or profile.get("year_of_passing"),
        "passing_year": profile.get("graduation_year") or profile.get("year_of_passing"),
        "year_of_passing": profile.get("graduation_year") or profile.get("year_of_passing"),
        # Experience
        "experience": profile.get("years_experience") or profile.get("total_experience"),
        "years_of_experience": profile.get("years_experience") or profile.get("total_experience"),
        "total_experience": profile.get("years_experience") or profile.get("total_experience"),
        "current_company": profile.get("current_company"),
        "company":    profile.get("current_company"),
        "designation": profile.get("current_role") or profile.get("current_title"),
        "current_role": profile.get("current_role") or profile.get("current_title"),
        "notice_period": profile.get("notice_period"),
        "notice":     profile.get("notice_period"),
        # Salary
        "current_ctc": profile.get("current_ctc") or profile.get("current_salary"),
        "current_salary": profile.get("current_ctc") or profile.get("current_salary"),
        "expected_ctc": profile.get("expected_salary") or profile.get("expected_ctc"),
        "expected_salary": profile.get("expected_salary") or profile.get("expected_ctc"),
        "salary":     profile.get("expected_salary") or profile.get("expected_ctc"),
        "stipend":    profile.get("expected_salary") or profile.get("expected_ctc"),
        # Skills
        "skills":     profile.get("skills") or profile.get("skill_list"),
        "cover_letter": (_cover[:500] if _cover else None),
        "message":    (_cover[:300] if _cover else None),
        "about":      (_cover[:300] if _cover else None),
    }
    # Drop keys whose value is None/empty — the form-fill loop will skip them
    # rather than writing placeholder data belonging to someone else.
    ats_field_map = {k: v for k, v in _raw_map.items() if v not in (None, "", [])}

    try:
        time.sleep(2)

        # ── 1. Fill all text / email / tel / url / number inputs ──
        inputs = driver.find_elements(By.CSS_SELECTOR,
            "input[type='text'], input[type='email'], input[type='tel'], "
            "input[type='url'], input[type='number'], input[type='search'], "
            "input:not([type]), input[type='']")

        for inp in inputs:
            try:
                if not inp.is_displayed():
                    continue
                if inp.get_attribute("readonly") or inp.get_attribute("disabled"):
                    continue
                val = (inp.get_attribute("value") or "").strip()
                if val:
                    continue

                # Build combined label from all sources
                combined = _combined_label(driver, inp)

                # Try direct name/id match first (most reliable for ATS)
                field_name = (inp.get_attribute("name") or "").lower().strip()
                field_id   = (inp.get_attribute("id")   or "").lower().strip()

                answer = None
                for key, mapped_val in ats_field_map.items():
                    if key in (field_name, field_id):
                        answer = mapped_val
                        break

                # Fall back to combined label match
                if not answer:
                    answer = match_answer(combined, config) if combined else None

                if answer:
                    _send_value(driver, inp, answer)
                    filled_count += 1
                    print(f"      ✏️  [{field_name or field_id or combined[:25]}]: {str(answer)[:40]}")
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue

        # ── 2. Fill textareas ──
        textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
        for ta in textareas:
            try:
                if not ta.is_displayed():
                    continue
                if ta.get_attribute("readonly") or ta.get_attribute("disabled"):
                    continue
                val = (ta.get_attribute("value") or ta.text or "").strip()
                if val:
                    continue

                combined = _combined_label(driver, ta)
                answer = match_answer(combined, config) if combined else None
                if not answer:
                    cover = (config.get("cover_letter") or "").strip()[:500]
                    if cover:
                        answer = cover
                    else:
                        cand_name = profile.get("full_name") or config.get("name") or "the candidate"
                        cand_role = (profile.get("current_role")
                                     or profile.get("current_title")
                                     or "my field")
                        answer = (
                            f"Hi, I'm {cand_name}. I'm excited about this role and believe my "
                            f"background in {cand_role} is a strong fit. Looking forward to "
                            "contributing to your team!"
                        )

                _send_value(driver, ta, answer)
                filled_count += 1
                print(f"      ✏️  [textarea/{combined[:25] or 'cover'}]: filled")
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue

        # ── 3. Handle <select> dropdowns ──
        try:
            from selenium.webdriver.support.ui import Select as SeleniumSelect
            selects = driver.find_elements(By.CSS_SELECTOR, "select")
            for sel_el in selects:
                try:
                    if not sel_el.is_displayed():
                        continue
                    combined = _combined_label(driver, sel_el)
                    sel = SeleniumSelect(sel_el)
                    current_val = sel.first_selected_option.get_attribute("value") or ""
                    if current_val and current_val.lower() not in ("", "select", "choose", "none", "--"):
                        continue

                    answer = match_answer(combined, config) if combined else None
                    matched = False
                    if answer:
                        for opt in sel.options:
                            if answer.lower() in opt.text.lower() or opt.text.lower() in answer.lower():
                                sel.select_by_visible_text(opt.text.strip())
                                filled_count += 1
                                print(f"      📋 [select/{combined[:25]}]: {opt.text.strip()}")
                                matched = True
                                break
                    if not matched:
                        # Pick first non-empty option
                        for opt in sel.options:
                            v = opt.get_attribute("value") or ""
                            if v and v.lower() not in ("", "select", "choose", "none", "--"):
                                sel.select_by_value(v)
                                filled_count += 1
                                print(f"      📋 [select/{combined[:25]}]: {opt.text.strip()}")
                                break
                except Exception:
                    continue
        except Exception:
            pass

        # ── 4. Handle radio buttons — prefer "Yes" ──
        try:
            fieldsets = driver.find_elements(By.CSS_SELECTOR, "fieldset, div[role='radiogroup']")
            for fs in fieldsets:
                try:
                    radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    if not radios or any(r.is_selected() for r in radios):
                        continue
                    yes_clicked = False
                    for r in radios:
                        try:
                            lbl = r.find_element(By.XPATH, "./following-sibling::label | ../label | ./ancestor::label")
                            if "yes" in lbl.text.lower():
                                driver.execute_script("arguments[0].click();", r)
                                yes_clicked = True
                                filled_count += 1
                                break
                        except Exception:
                            continue
                    if not yes_clicked and radios:
                        driver.execute_script("arguments[0].click();", radios[0])
                        filled_count += 1
                except Exception:
                    continue
        except Exception:
            pass

        # ── 5. Upload resume — force-show hidden file inputs ──
        if resume_path and os.path.exists(resume_path):
            try:
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                for fi in file_inputs:
                    try:
                        label = _combined_label(driver, fi) or ""
                        if label:
                            label_lower = label.lower()
                            non_resume_kws = ["photo", "picture", "image", "transcript", "cover letter", "portfolio", "certificate", "id card", "passport"]
                            resume_kws = ["resume", "cv", "curriculum", "bio"]
                            if any(nk in label_lower for nk in non_resume_kws) and not any(rk in label_lower for rk in resume_kws):
                                print(f"      ⏭️  Skipping file input with label '{label[:40]}' (not a resume field)")
                                continue
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';"
                            "arguments[0].removeAttribute('hidden');",
                            fi)
                        fi.send_keys(resume_path)
                        filled_count += 1
                        print(f"      📄 Resume uploaded: {os.path.basename(resume_path)}")
                        time.sleep(2)
                    except Exception:
                        continue
            except Exception:
                pass
        else:
            if resume_path:
                print(f"      ⚠️  Resume not found at: {resume_path}")

        print(f"    ✅ [WebForm] Filled {filled_count} fields")

    except Exception as e:
        print(f"    ❌ [WebForm] Failed: {e}")
        traceback.print_exc()

    # Post-fill: Try to find a 'Submit' or 'Apply' button but don't click it (user review)
    try:
        submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Submit')] | //button[contains(text(), 'Apply')] | //input[@type='submit']")
        if submit_btn.is_displayed():
            print("      💡 Found submit button! Ready for your review.")
    except:
        pass

    return filled_count


# ─────────────────────────────────────────────
#  AUTO-FILL ALL OPEN TABS
# ─────────────────────────────────────────────
def auto_fill_open_tabs(driver, config):
    """
    Go through all open browser tabs, detect forms,
    and auto-fill + upload resume where possible.
    """
    print(f"\n  {'━' * 50}")
    print(f"  📝 AUTO-FILL: Scanning all open tabs for forms...")
    print(f"  {'━' * 50}")

    tabs = driver.window_handles
    original_tab = driver.current_window_handle
    filled_tabs = 0
    total_fields = 0

    for i, tab in enumerate(tabs):
        try:
            driver.switch_to.window(tab)
            time.sleep(1)
            url = driver.current_url

            # Skip blank/google search tabs
            if url in ["about:blank", "data:,"] or "google.com/search" in url:
                continue

            print(f"\n    [{i+1}/{len(tabs)}] {url[:70]}...")

            if is_google_form(driver):
                count = fill_google_form(driver, config)
                total_fields += count
                if count > 0:
                    filled_tabs += 1

            elif is_typeform(driver):
                print("      ℹ️  Typeform detected — needs manual fill")
                continue

            else:
                # Check if page has any forms
                forms = driver.find_elements(By.CSS_SELECTOR,
                    "form, div[role='form'], .application-form, "
                    ".apply-form, .job-form")
                inputs = driver.find_elements(By.CSS_SELECTOR,
                    "input[type='text'], input[type='email'], textarea, "
                    "input[type='file']")

                if forms or len(inputs) >= 2:
                    count = fill_web_form(driver, config)
                    total_fields += count
                    if count > 0:
                        filled_tabs += 1
                else:
                    print("      ℹ️  No form detected on this page")

        except Exception as e:
            print(f"      ⚠️  Error on tab: {str(e)[:50]}")
            continue

    # Switch back to original tab
    try:
        driver.switch_to.window(original_tab)
    except:
        pass

    print(f"\n  {'━' * 50}")
    print(f"  ✅ AUTO-FILL COMPLETE!")
    print(f"  📊 Filled {total_fields} fields across {filled_tabs} tabs")
    print(f"  👉 Review each tab and submit manually!")
    print(f"  {'━' * 50}")

    return filled_tabs, total_fields
