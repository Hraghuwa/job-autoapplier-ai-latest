"""
LinkedIn Easy Apply Automation Module (AI-Powered)
Strategy: Stay on search results page, click each job card in the left panel,
then click Easy Apply in the right detail panel — no page navigation needed.
Uses Gemini AI for intelligent form field answers.
"""

import time
import random
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, ElementNotInteractableException,
    ElementClickInterceptedException, TimeoutException,
    StaleElementReferenceException, JavascriptException
)
import agent_vision
import job_finder
import google_form_filler

def _retry(fn, retries=3, delay=2, label=""):
    """Retry a lambda up to `retries` times on transient Selenium exceptions."""
    for attempt in range(retries):
        try:
            return fn()
        except (StaleElementReferenceException, ElementClickInterceptedException) as e:
            if attempt == retries - 1:
                raise
            print(f"  ⚠️  Retrying ({attempt+1}/{retries}) {label}: {type(e).__name__}")
            time.sleep(delay)


# ─────────────────────────────────────────────
#  GEMINI AI for smart form filling
# ─────────────────────────────────────────────
_ai_client = None

def _ask_ai(question, config):
    """Use Gemini AI to answer a LinkedIn form question intelligently."""
    global _ai_client
    api_key = config.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    try:
        if _ai_client is None:
            from google import genai
            _ai_client = genai.Client(api_key=api_key)

        profile = config.get("profile", {})
        name = config.get("name", profile.get("full_name", "the applicant"))
        prompt = f"""You are filling a LinkedIn job application form for {name}.
Read the EXACT question carefully and answer with ONLY the value, nothing else.

Applicant profile:
- Name: {name}
- Email: {config.get("email", profile.get("email", ""))}
- Phone: {config.get("phone", profile.get("phone", ""))}
- Location: {profile.get("location", "")}
- Skills: {profile.get("skills", "")}
- LinkedIn: {profile.get("linkedin", "")}
- Experience: {profile.get("experience_summary", profile.get("experience", ""))}
- Education: {profile.get("education", "")}
- 10th marks: {profile.get("marks_10th", "80")}
- 12th marks: {profile.get("marks_12th", "78")}
- Graduation CGPA: {profile.get("graduation_cgpa", "7.5")}
- Current CGPA: {profile.get("current_cgpa", profile.get("graduation_cgpa", "7.0"))}
- Notice period: {profile.get("notice_period", "30 days")}
- Expected salary: {profile.get("expected_salary", profile.get("salary", ""))}
- Current/prev salary: {profile.get("current_salary", "")}
- Years of experience: {profile.get("years_of_experience", "")}

Form question: "{question}"

CRITICAL RULES:
- If asking for 10th/SSC/Class X marks → use 10th marks above
- If asking for 12th/HSC/Class XII marks → use 12th marks above
- If asking for graduation/UG CGPA → use graduation CGPA above
- If asking for current/PG CGPA → use current CGPA above
- If asking for generic "marks" or "percentage" → use 12th marks
- If asking for generic "CGPA/GPA" → use graduation CGPA
- If asking about experience with a tool/skill → answer years of experience
- If yes/no question → answer "Yes" if applicant likely qualifies
- If asking about salary/CTC/stipend → use expected salary
- If asking about current salary → use current/prev salary
- If asking about notice period → use notice period above
- If asking about location/city → use location above
- Do NOT say "I" — just give the direct answer value

Output ONLY the answer, nothing else."""

        response = _ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        answer = response.text.strip().strip('"').strip("'")
        if answer and len(answer) < 200:
            return answer
    except Exception:
        pass
    return None


def login(driver, email, password):
    print("\n[LinkedIn] Logging in...")

    if not email or not password or password.startswith("YOUR_"):
        print("[LinkedIn] ❌ Credentials not set! Add them in the Credentials page.")
        return False

    driver.get("https://www.linkedin.com/login")
    time.sleep(3)

    try:
        # Check for alternative login form IDs
        try:
            email_field = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            pass_field = driver.find_element(By.ID, "password")
        except:
            email_field = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "session_key"))
            )
            pass_field = driver.find_element(By.ID, "session_password")

        email_field.clear()
        email_field.send_keys(email)

        pass_field.clear()
        pass_field.send_keys(password)

        try:
            driver.find_element(By.XPATH, "//button[@type='submit']").click()
        except:
            pass_field.send_keys(Keys.RETURN)
            
        print("[LinkedIn] Submitted login form, waiting for response...")
        time.sleep(10)
    except Exception as e:
        print(f"[LinkedIn] ❌ Login error: {e}")
        return False

    url = driver.current_url
    if "feed" in url or "mynetwork" in url or "jobs" in url:
        print("[LinkedIn] ✅ Logged in successfully!")
        return True
    elif "checkpoint" in url or "challenge" in url or "security" in url:
        print("[LinkedIn] ⚠️  Security challenge detected. Please solve it manually in the browser.")
        print("[LinkedIn] ⏳ Waiting 60 seconds for you to complete the challenge...")
        time.sleep(60)
        # Re-check URL after user completes the challenge
        url = driver.current_url
        if "feed" in url or "mynetwork" in url or "jobs" in url:
            print("[LinkedIn] ✅ Challenge solved! Logged in successfully.")
            return True
        print(f"[LinkedIn] ❌ Challenge not resolved. Current URL: {url}")
        return False
    else:
        print(f"[LinkedIn] ⚠️  Login may have failed. Current URL: {url}")
        return False


def try_click(driver, element):
    """Try multiple methods to click an element."""
    try:
        element.click()
        return True
    except (ElementClickInterceptedException, ElementNotInteractableException):
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except:
        pass
    try:
        ActionChains(driver).move_to_element(element).click().perform()
        return True
    except:
        pass
    return False


def fill_modal_fields(driver, config):
    """Auto-fill any empty fields in the Easy Apply modal using profile data from config."""
    filled_something = False
    profile = config.get("profile", {})

    # Field matching rules: (keywords_to_match, value_to_fill)
    # ⚠️ ORDER MATTERS — more specific rules FIRST, generic ones last
    # Derive full_name and split for first/last
    full_name = profile.get("full_name", config.get("name", ""))
    name_parts = full_name.split(" ", 1) if full_name else ["", ""]
    first_name = profile.get("first_name", name_parts[0])
    last_name = profile.get("last_name", name_parts[1] if len(name_parts) > 1 else "")

    field_rules = [
        # ── Name fields ──
        (["first name", "given name"], first_name),
        (["last name", "surname", "family name"], last_name),
        (["full name", "your name", "candidate name"], full_name),

        # ── Contact ──
        (["phone", "mobile", "contact number", "tel", "whatsapp"], profile.get("phone", config.get("phone", ""))),
        (["email", "e-mail", "mail id"], profile.get("email", config.get("email", ""))),
        (["linkedin", "profile url", "portfolio"], profile.get("linkedin", "")),

        # ── Location ──
        (["city", "current city", "hometown"], profile.get("location", "")),
        (["state"], profile.get("state", "")),
        (["country"], profile.get("country", "India")),
        (["address", "street", "location"], profile.get("address", profile.get("location", ""))),
        (["pin", "zip", "postal"], profile.get("pin_code", "")),

        # ── Education marks — SPECIFIC rules first! ──
        (["10th", "ssc", "class 10", "class x", "xth", "tenth", "matric"],
         profile.get("tenth_marks", profile.get("marks_10th", ""))),
        (["12th", "hsc", "class 12", "class xii", "xiith", "twelfth", "inter", "plus two", "+2", "senior secondary"],
         profile.get("twelfth_marks", profile.get("marks_12th", ""))),
        (["mba cgpa", "mba gpa", "current cgpa", "pg cgpa", "postgrad"],
         profile.get("mba_cgpa", profile.get("current_cgpa", ""))),
        (["grad cgpa", "ug cgpa", "undergrad", "bachelor", "btech", "b.tech", "ba ", "bsc", "b.sc", "b.com"],
         profile.get("grad_cgpa", profile.get("graduation_cgpa", ""))),
        (["cgpa", "gpa"], profile.get("grad_cgpa", profile.get("graduation_cgpa", ""))),
        (["percentage", "percent", "%", "marks", "score", "grade"],
         profile.get("twelfth_marks", profile.get("marks_12th", ""))),

        # ── Education details ──
        (["university", "college", "school", "institution"], profile.get("university", profile.get("education", ""))),
        (["degree", "qualification", "course"], profile.get("degree", "")),
        (["major", "field of study", "specialization", "branch", "stream"], profile.get("specialization", "")),
        (["graduation", "passing year", "end year", "year of completion", "batch"], profile.get("graduation_year", "")),
        (["start year", "joining year", "enrollment"], profile.get("enrollment_year", "")),

        # ── Experience & duration ──
        (["years of experience", "total experience", "work experience", "relevant experience"],
         profile.get("years_experience", profile.get("years_of_experience", ""))),
        (["duration", "internship period", "period", "how long", "months"], profile.get("internship_duration", "")),
        (["notice period", "joining time", "notice"], profile.get("notice_period", "")),
        (["current company", "current organization", "employer", "company name"], profile.get("current_company", "")),
        (["current role", "current title", "designation", "job title", "position"], profile.get("current_role", "")),
        (["available", "availability", "start date", "join date", "earliest"], profile.get("availability", "")),

        # ── Salary & compensation ──
        (["current salary", "current ctc", "present salary", "present ctc", "last drawn"],
         profile.get("current_salary", profile.get("previous_salary", ""))),
        (["expected salary", "expected ctc", "salary expectation"],
         profile.get("expected_salary", "")),
        (["salary", "ctc", "compensation", "stipend"], profile.get("expected_salary", "")),

        # ── Authorization ──
        (["authorized", "authorization", "legally", "eligible", "visa", "permit"],
         profile.get("legally_authorized", "Yes")),
        (["sponsorship", "sponsor"], profile.get("require_sponsorship", "No")),
        (["relocat", "willing to relocate"], profile.get("willing_to_relocate", "Yes")),
        (["how did you hear", "source", "referral", "where did you"], "LinkedIn"),

        # ── Skills & Certifications ──
        (["skill", "expertise", "competenc", "proficien"], profile.get("skills", "")),
        (["certif", "credential"], profile.get("certifications", "")),
    ]

    # Fill empty text inputs
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR,
            "div.jobs-easy-apply-modal input[type='text'], "
            "div.artdeco-modal input[type='text'], "
            "div.jobs-easy-apply-content input[type='text'], "
            "div[role='dialog'] input[type='text']")
        for inp in inputs:
            try:
                val = (inp.get_attribute("value") or "").strip()
                if val:
                    continue

                # Build label text from all available sources
                inp_id = inp.get_attribute("id") or ""
                aria = inp.get_attribute("aria-label") or ""
                placeholder = inp.get_attribute("placeholder") or ""
                label_text = ""
                try:
                    label_el = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                    label_text = label_el.text
                except:
                    pass
                combined = f"{label_text} {aria} {inp_id} {placeholder}".lower()

                # Match against field rules
                matched = False
                for keywords, value in field_rules:
                    if value and any(kw in combined for kw in keywords):
                        inp.clear()
                        inp.send_keys(value)
                        filled_something = True
                        matched = True
                        print(f"    [Fill] {label_text or aria or inp_id}: {value[:30]}")
                        break

                if not matched:
                    # AI-powered fallback: ask Gemini to answer the question
                    question = label_text or aria or placeholder or combined
                    ai_answer = _ask_ai(question, config)
                    if ai_answer:
                        inp.clear()
                        inp.send_keys(ai_answer)
                        filled_something = True
                        print(f"    [AI] {question[:40]}: {ai_answer[:30]}")
                    # Leave unmatched, non-AI-answered fields blank rather than guessing

            except (StaleElementReferenceException, Exception):
                continue
    except:
        pass

    # Fill number inputs
    try:
        num_inputs = driver.find_elements(By.CSS_SELECTOR,
            "div.jobs-easy-apply-modal input[type='number'], "
            "div.artdeco-modal input[type='number'], "
            "div[role='dialog'] input[type='number']")
        for inp in num_inputs:
            try:
                val = (inp.get_attribute("value") or "").strip()
                if val and val != "0":
                    continue
                aria = (inp.get_attribute("aria-label") or "").lower()
                label_text = ""
                try:
                    inp_id = inp.get_attribute("id") or ""
                    label_el = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                    label_text = label_el.text.lower()
                except:
                    pass
                combined = f"{label_text} {aria}".lower()

                if any(w in combined for w in ["month", "duration", "period", "internship length"]):
                    val = profile.get("internship_duration", "3").split()[0]
                    inp.clear()
                    inp.send_keys(val)
                    print(f"    [Fill] Duration/months: {val}")
                elif any(w in combined for w in ["experience", "year"]):
                    val = profile.get("years_experience", profile.get("years_of_experience", ""))
                    if not val:
                        val = _ask_ai(combined, config) or "1"
                    inp.clear()
                    inp.send_keys(str(val))
                    print(f"    [Fill] Years experience: {val}")
                elif any(w in combined for w in ["gpa", "cgpa", "grade"]):
                    val = profile.get("grad_cgpa", profile.get("graduation_cgpa", profile.get("cgpa", "")))
                    if not val:
                        val = _ask_ai(combined, config) or "7.0"
                    inp.clear()
                    inp.send_keys(str(val))
                    print(f"    [Fill] GPA: {val}")
                elif any(w in combined for w in ["salary", "ctc", "stipend"]):
                    val = profile.get("expected_salary", "")
                    if not val:
                        val = _ask_ai(combined, config) or "0"
                    inp.clear()
                    inp.send_keys(str(val))
                    print(f"    [Fill] Salary: {val}")
                else:
                    ai_val = _ask_ai(combined, config)
                    final = ai_val if ai_val and ai_val.isdigit() else "0"
                    inp.clear()
                    inp.send_keys(final)
                    print(f"    [Fill] Numeric ({combined[:30]}): {final}")
                filled_something = True
            except:
                continue
    except:
        pass

    # Fill textareas (cover letter etc.)
    try:
        textareas = driver.find_elements(By.CSS_SELECTOR,
            "div.jobs-easy-apply-modal textarea, "
            "div.artdeco-modal textarea, "
            "div[role='dialog'] textarea")
        for ta in textareas:
            try:
                val = (ta.get_attribute("value") or "").strip()
                if not val:
                    ta.send_keys(config.get("cover_letter",
                        "I am excited to apply for this opportunity and believe my skills align well with the role."))
                    filled_something = True
                    print("    [Fill] Cover letter / text area")
            except:
                continue
    except:
        pass

    # Handle dropdowns — select "Yes" if available, otherwise first non-empty option
    try:
        selects = driver.find_elements(By.CSS_SELECTOR,
            "div.jobs-easy-apply-modal select, "
            "div.artdeco-modal select, "
            "div[role='dialog'] select")
        for sel_elem in selects:
            try:
                sel = Select(sel_elem)
                current = sel.first_selected_option.get_attribute("value") or ""
                if not current or current == "Select an option":
                    # Try to select "Yes" first
                    yes_found = False
                    for opt in sel.options:
                        if opt.text.strip().lower() == "yes":
                            sel.select_by_visible_text(opt.text.strip())
                            yes_found = True
                            filled_something = True
                            print(f"    [Fill] Dropdown: Yes")
                            break
                    if not yes_found:
                        for opt in sel.options:
                            v = opt.get_attribute("value")
                            if v and v != "Select an option" and v != "":
                                sel.select_by_value(v)
                                filled_something = True
                                print(f"    [Fill] Dropdown: {opt.text}")
                                break
            except:
                continue
    except:
        pass

    # Handle radio buttons — prefer "Yes" option, else select first
    try:
        fieldsets = driver.find_elements(By.CSS_SELECTOR,
            "div.jobs-easy-apply-modal fieldset, "
            "div.artdeco-modal fieldset, "
            "div[role='dialog'] fieldset")
        for fieldset in fieldsets:
            try:
                radios = fieldset.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                if radios and not any(r.is_selected() for r in radios):
                    # Try to find "Yes" option first
                    yes_clicked = False
                    for radio in radios:
                        try:
                            label = radio.find_element(By.XPATH,
                                "./ancestor::div[contains(@class,'radio')]//label | "
                                "./following-sibling::label | ../label")
                            if label.text.strip().lower() == "yes":
                                try_click(driver, label)
                                yes_clicked = True
                                filled_something = True
                                print("    [Fill] Radio: Yes")
                                break
                        except:
                            continue
                    if not yes_clicked:
                        # Select first option
                        try:
                            label = radios[0].find_element(By.XPATH,
                                "./ancestor::div[contains(@class,'radio')]//label | "
                                "./following-sibling::label | ../label")
                            try_click(driver, label)
                        except:
                            try_click(driver, radios[0])
                        filled_something = True
                        print("    [Fill] Radio: first option")
            except:
                continue
    except:
        pass

    # Handle checkboxes
    try:
        checkboxes = driver.find_elements(By.CSS_SELECTOR,
            "div.jobs-easy-apply-modal input[type='checkbox'], "
            "div.artdeco-modal input[type='checkbox'], "
            "div[role='dialog'] input[type='checkbox']")
        for cb in checkboxes:
            try:
                if not cb.is_selected():
                    try_click(driver, cb)
                    filled_something = True
                    print("    [Fill] Checkbox checked")
            except:
                continue
    except:
        pass

    return filled_something


def process_easy_apply_modal(driver, config):
    """Walk through the multi-step Easy Apply modal until submitted."""
    max_steps = 15
    _stop = config.get("_stop_event")

    for step in range(max_steps):
        if _stop and _stop.is_set():
            print("    [Modal] 🛑 Stop requested — closing modal.")
            try:
                driver.find_element(By.CSS_SELECTOR,
                    "button[aria-label='Dismiss'], button.artdeco-modal__dismiss").click()
            except Exception:
                pass
            return "stopped"
        time.sleep(2)

        # Check if modal is still open
        modal = None
        try:
            modal = driver.find_element(By.CSS_SELECTOR,
                "div.jobs-easy-apply-modal, div.artdeco-modal--is-open, "
                "div[role='dialog']")
        except NoSuchElementException:
            print("    [Modal] Modal closed (may have been one-click apply)")
            return "closed"

        # Check for success message (application already submitted)
        try:
            success = driver.find_elements(By.XPATH,
                "//*[contains(text(),'Application submitted') or "
                "contains(text(),'application was sent') or "
                "contains(text(),'You applied')]")
            if any(s.is_displayed() for s in success):
                print("    ✅ Application submitted!")
                # Dismiss the success dialog
                try:
                    dismiss = driver.find_element(
                        By.XPATH, "//button[contains(@aria-label,'Dismiss')]")
                    try_click(driver, dismiss)
                except:
                    pass
                return "submitted"
        except:
            pass

        # Handle resume upload if file input is present
        try:
            upload_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            for upload_input in upload_inputs:
                try:
                    driver.execute_script(
                        "arguments[0].style.display='block'; arguments[0].style.opacity='1';",
                        upload_input)
                    upload_input.send_keys(config["resume_path"])
                    print("    [Resume] Uploaded")
                    time.sleep(2)
                except:
                    pass
        except:
            pass

        # Fill any empty form fields
        fill_modal_fields(driver, config)

        # Try to click action buttons — search for ALL visible buttons in modal first
        clicked = False

        # Strategy: Find all buttons in the modal footer and click the right one
        all_modal_buttons = []
        try:
            all_modal_buttons = driver.find_elements(By.CSS_SELECTOR,
                "div.jobs-easy-apply-modal button, "
                "div.artdeco-modal button, "
                "div[role='dialog'] button, "
                "div.jobs-easy-apply-content button")
        except:
            pass

        # Priority order: Submit > Review > Next > Continue
        priority_texts = [
            "Submit application", "Submit",
            "Review", "Next", "Continue"
        ]

        for priority_text in priority_texts:
            if clicked:
                break
            for btn in all_modal_buttons:
                try:
                    if not btn.is_displayed() or not btn.is_enabled():
                        continue
                    btn_text = btn.text.strip()
                    aria_label = btn.get_attribute("aria-label") or ""

                    if (priority_text.lower() in btn_text.lower() or
                        priority_text.lower() in aria_label.lower()):
                        print(f"    [Step {step+1}] Clicking: '{btn_text}' (aria: '{aria_label}')")
                        try_click(driver, btn)
                        time.sleep(2)
                        clicked = True

                        if "submit" in priority_text.lower():
                            print("    ✅ Submitted!")
                            time.sleep(1)
                            # Dismiss success dialog
                            try:
                                dismiss = driver.find_element(
                                    By.XPATH, "//button[contains(@aria-label,'Dismiss')]")
                                try_click(driver, dismiss)
                            except:
                                pass
                            return "submitted"
                        break
                except (StaleElementReferenceException, Exception):
                    continue

        if not clicked:
            # Vision fallback: ask Gemini what to do
            vision_action = agent_vision.decide_action(driver, config, 
                f"Multi-step form step {step+1}, looking for Next/Review/Submit")
            if vision_action:
                print(f"    👁️ Vision says: {vision_action}")
                if vision_action in ("SKIP", "ALREADY_APPLIED"):
                    return "skipped"
            # XPath fallback
            for btn_text in priority_texts:
                try:
                    fallback_btns = driver.find_elements(By.XPATH,
                        f"//button[contains(normalize-space(),'{btn_text}')]")
                    for btn in fallback_btns:
                        if btn.is_displayed() and btn.is_enabled():
                            print(f"    [Step {step+1}] Fallback click: '{btn.text.strip()}'")
                            try_click(driver, btn)
                            time.sleep(2)
                            clicked = True

                            if "submit" in btn_text.lower():
                                print("    ✅ Submitted!")
                                time.sleep(1)
                                try:
                                    dismiss = driver.find_element(
                                        By.XPATH, "//button[contains(@aria-label,'Dismiss')]")
                                    try_click(driver, dismiss)
                                except:
                                    pass
                                return "submitted"
                            break
                    if clicked:
                        break
                except:
                    continue

        if not clicked:
            print(f"    [Step {step+1}] No actionable button found in modal")
            # Debug: print all visible buttons
            try:
                for btn in all_modal_buttons:
                    if btn.is_displayed():
                        print(f"      [Debug] Button: '{btn.text.strip()}' aria='{btn.get_attribute('aria-label')}'")
            except:
                pass

        # Check for validation errors
        try:
            errors = driver.find_elements(By.CSS_SELECTOR,
                "div.artdeco-inline-feedback--error, "
                "span.artdeco-inline-feedback__message")
            if errors and any(e.is_displayed() for e in errors):
                print("    ⚠️  Validation errors found, re-filling fields...")
                fill_modal_fields(driver, config)
                time.sleep(1)
        except:
            pass

    return "stuck"


def dismiss_modal(driver):
    """Close any open Easy Apply modal."""
    try:
        dismiss_btns = driver.find_elements(By.CSS_SELECTOR,
            "button[aria-label='Dismiss'], button[aria-label='Discard']")
        for btn in dismiss_btns:
            if btn.is_displayed():
                try_click(driver, btn)
                time.sleep(1)
        # Confirm discard if asked
        try:
            discard = driver.find_element(
                By.XPATH, "//button[contains(normalize-space(),'Discard')]")
            if discard.is_displayed():
                try_click(driver, discard)
                time.sleep(1)
        except:
            pass
    except:
        pass


def _is_title_relevant(job_title, keywords, config=None):
    """
    Relaxed stem-based title relevance check.

    Algorithm:
    1. At least ONE keyword must have a partial stem match against the title.
       Stem matching uses the first 5 chars so 'manage' matches 'manager',
       'intern' matches 'internship', 'market' matches 'marketing', etc.
       Requires at least HALF the keyword's meaningful words to match.
    2. Seniority check only fires when user is explicitly searching for
       internship/entry-level roles — prevents senior roles from slipping in.
    3. If keyword implies internship, title must also be internship-level.
    No hard tech blocklist — that was causing all MBA/management roles to be rejected.
    """
    import re as _re

    title_lower = job_title.lower().strip()
    if not title_lower:
        return False, "Empty title"

    cfg = config or {}
    employment_types = cfg.get("employment_types", [])
    searching_intern = (
        any(t.lower() in ("internship", "trainee") for t in employment_types)
        or any("intern" in kw.lower() or "trainee" in kw.lower() for kw in (keywords or []))
    )

    SENIORITY = [
        "senior", "sr.", "sr ", "lead", "principal", "director", "vp",
        "head", "chief", "staff", "architect", "president", "executive",
    ]
    INTERN_WORDS = ["intern", "trainee", "apprentice", "graduate", "fresher", "student"]

    def _stem_match(kw: str, title: str) -> bool:
        """
        Returns True if at least HALF the meaningful words from kw appear in title
        via 5-char stem prefix matching. This allows:
          'management' → stem 'manag' matches 'manager', 'managing'
          'marketing'  → stem 'marke' matches 'marketing', 'marketer'
          'internship' → stem 'inter' matches 'intern', 'internship'
        """
        words = [w for w in _re.split(r'\W+', kw.lower()) if len(w) > 3]
        if not words:
            return False
        matched = sum(
            1 for w in words
            if _re.search(r'\b' + _re.escape(w[:5]), title)
        )
        return matched >= max(1, len(words) // 2)

    # ── RULE 1: stem-based keyword match ─────────────────────────────────────
    for kw in (keywords or []):
        if not _stem_match(kw, title_lower):
            continue  # not enough stem overlap — try next keyword

        kw_lower = kw.lower()
        title_has_seniority = any(s.strip() in title_lower for s in SENIORITY)
        kw_has_seniority    = any(s.strip() in kw_lower    for s in SENIORITY)

        # Only block senior titles when user is explicitly searching entry-level/intern
        if title_has_seniority and not kw_has_seniority and searching_intern:
            return False, f"Senior role blocked for intern search: '{job_title}'"

        # If keyword implies internship, title must also be an internship
        kw_is_intern    = any(w in kw_lower    for w in INTERN_WORDS)
        title_is_intern = any(w in title_lower for w in INTERN_WORDS)
        if kw_is_intern and not title_is_intern:
            return False, f"Intern keyword but title '{job_title}' is not an internship"

        return True, f"Matched keyword: {kw}"

    # ── RULE 2: if explicitly searching for internships, title must say so ───
    if searching_intern and not any(w in title_lower for w in INTERN_WORDS):
        return False, "Not an internship role"

    return False, "No keywords matched"


def handle_external_application(driver, config, original_handles, linkedin_tab):
    """
    Detects if clicking Apply opened a new external tab.
    If so: switches to it, auto-fills the form, uploads resume, tries to submit.
    Returns 'submitted', 'filled' (needs manual submit), or None (no external tab).
    """
    time.sleep(3)
    current_handles = driver.window_handles

    new_tabs = [h for h in current_handles if h not in original_handles]
    if not new_tabs:
        return None  # No external tab opened — must be Easy Apply modal

    ext_tab = new_tabs[-1]
    print(f"  🌐 External application tab detected — switching to it...")
    driver.switch_to.window(ext_tab)

    try:
        # Wait for page to fully load
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(3)
        url = driver.current_url
        print(f"  🔗 External URL: {url[:80]}")

        import google_form_filler

        # Walk through up to 8 steps (multi-step ATS forms)
        submitted = False
        for step in range(8):
            if google_form_filler.is_google_form(driver):
                count = google_form_filler.fill_google_form(driver, config)
            else:
                count = google_form_filler.fill_web_form(driver, config)

            print(f"  ✏️  Step {step+1}: filled {count} fields")
            time.sleep(1)

            # Try Submit first, then Next/Continue to advance multi-step form
            clicked = False
            for btn_text in ["Submit Application", "Submit", "Apply", "Send Application",
                             "Next", "Continue", "Next Step", "Proceed"]:
                try:
                    btns = driver.find_elements(By.XPATH,
                        f"//button[contains(normalize-space(),'{btn_text}')] | "
                        f"//input[@type='submit'] | "
                        f"//a[contains(normalize-space(),'{btn_text}')]")
                    for btn in btns:
                        if btn.is_displayed() and btn.is_enabled():
                            print(f"  👆 Clicking: '{btn.text.strip() or btn_text}'")
                            try_click(driver, btn)
                            time.sleep(3)
                            clicked = True
                            if any(w in btn_text.lower() for w in ["submit", "apply", "send"]):
                                submitted = True
                            break
                except Exception:
                    continue
                if clicked:
                    break

            if submitted:
                break
            if not clicked:
                print(f"  ℹ️  No next/submit button found at step {step+1} — stopping")
                break

        # Keep the external tab open so user can review / submit manually
        # Switch back to LinkedIn tab
        driver.switch_to.window(linkedin_tab)
        time.sleep(1)

        return "submitted" if submitted else "filled"

    except Exception as e:
        print(f"  ❌ External tab error: {e}")
        try:
            driver.switch_to.window(linkedin_tab)
        except Exception:
            pass
        return None


def apply_from_search_page(driver, config, applied_count, max_jobs, current_keywords=None):
    """
    Stay on the search results page.
    Click each job card in the left panel → find Easy Apply button in the right panel → apply.
    Re-discovers cards after each application to avoid stale element issues.
    Only applies to jobs whose titles are relevant to the current search keywords.
    """
    time.sleep(3)

    # Scroll down to load all job cards
    try:
        results_container = driver.find_element(By.CSS_SELECTOR,
            "div.jobs-search-results-list, div.scaffold-layout__list")
        for _ in range(5):
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;", results_container)
            time.sleep(1)
        driver.execute_script("arguments[0].scrollTop = 0;", results_container)
        time.sleep(1)
    except Exception:
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

    CARD_SELECTORS = (
        "div.job-card-container, "
        "li.jobs-search-results__list-item, "
        "div.jobs-search-results-list__list-item, "
        "li.ember-view.occludable-update, "
        "div.scaffold-layout__list-item"
    )

    def find_cards():
        cards = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTORS)
        if not cards:
            cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
        return cards

    initial_cards = find_cards()
    total_count = len(initial_cards)
    print(f"  [Search] Found {total_count} job cards on this page")

    if not total_count:
        print("  ⚠️  No job cards found. Page might not have loaded properly.")
        try:
            print(f"  [Debug] Page title: {driver.title}")
        except:
            pass
        return applied_count

    card_index = 0
    processed = 0
    _stop = config.get("_stop_event")  # threading.Event — set when user clicks Stop

    while card_index < total_count and applied_count < max_jobs:
        # ── Stop check: bail out immediately when user clicks Stop ──
        if _stop and _stop.is_set():
            print("  [LinkedIn] 🛑 Stop requested — exiting card loop.")
            return applied_count

        # Re-find cards fresh each iteration to avoid stale elements
        current_cards = find_cards()
        if card_index >= len(current_cards):
            print(f"  [Info] No more cards to process (index {card_index} >= {len(current_cards)})")
            break

        card = current_cards[card_index]
        card_index += 1
        processed += 1

        try:
            # Scroll the card into view
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", card)
            time.sleep(1)

            # Click the job card to load details in right panel
            try_click(driver, card)
            time.sleep(3)

            # Get job title from the right panel
            job_title = "Unknown"
            try:
                title_el = driver.find_element(By.CSS_SELECTOR,
                    "div.jobs-details h1, "
                    "div.job-details-jobs-unified-top-card h1, "
                    "h1.t-24, h1.job-title, "
                    "div.jobs-unified-top-card h1, "
                    "a.job-card-list__title, "
                    "h2.job-card-list__title")
                job_title = title_el.text.strip()[:60]
            except:
                try:
                    job_title = card.text.split("\n")[0][:60]
                except:
                    pass

            print(f"\n  [{processed}/{total_count}] Checking: {job_title}")

            # ── Title relevance filter ──
            filter_keywords = current_keywords or config.get("keywords", [])
            is_relevant, reason = _is_title_relevant(job_title, filter_keywords, config)
            if not is_relevant:
                print(f"  ⏭️  Skipping (not relevant): {job_title} ({reason})")
                continue

            # ── Duration filter: only for internship searches + user set explicit duration ──
            _intern_types = {"internship", "trainee", "fresher"}
            _searching_intern = any(t.lower() in _intern_types for t in config.get("employment_types", []))
            _preferred_duration = config.get("internship_duration", "").lower().strip()
            _duration_strict = _preferred_duration and _preferred_duration not in ("", "any", "flexible")

            if _searching_intern and _duration_strict:
                try:
                    desc_el = driver.find_element(By.CSS_SELECTOR,
                        "div.jobs-description, article, div.job-details-jobs-unified-top-card")
                    desc_text = desc_el.text.lower()
                    if _preferred_duration not in desc_text:
                        print(f"  ⏭️  Skipping (duration mismatch: want '{_preferred_duration}'): {job_title}")
                        continue
                except Exception:
                    pass  # description not found, don't skip

            # Look for Easy Apply button in the right panel / detail area
            easy_apply_btn = None

            # Try multiple selectors for the Easy Apply button
            selectors = [
                "//button[contains(@class,'jobs-apply-button')]",
                "//button[contains(normalize-space(),'Easy Apply')]",
                "//button[contains(@aria-label,'Easy Apply')]",
                "//button[contains(@class,'jobs-apply-button') and contains(normalize-space(),'Apply')]",
                "//div[contains(@class,'jobs-details')]//button[contains(normalize-space(),'Apply')]",
                "//div[contains(@class,'job-details')]//button[contains(normalize-space(),'Apply')]",
            ]

            for sel in selectors:
                try:
                    btns = driver.find_elements(By.XPATH, sel)
                    for btn in btns:
                        if btn.is_displayed() and btn.is_enabled():
                            btn_text = btn.text.strip()
                            # Skip if it's an "Apply" that redirects externally
                            if "Easy" in btn_text or "Easy" in (btn.get_attribute("aria-label") or ""):
                                easy_apply_btn = btn
                                break
                            elif "Apply" in btn_text:
                                # Could be Easy Apply without the word "Easy" visible
                                easy_apply_btn = btn
                                break
                    if easy_apply_btn:
                        break
                except:
                    continue

            if not easy_apply_btn:
                # Last resort: wait and try one more time
                time.sleep(3)
                try:
                    easy_apply_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//button[contains(normalize-space(),'Easy Apply') or contains(normalize-space(),'Apply')]")
                        )
                    )
                except:
                    pass

            if not easy_apply_btn:
                print(f"  ⏭️  No Apply button found for: {job_title}")
                continue

            # Check if it says "Applied" (already applied)
            btn_text = easy_apply_btn.text.strip().lower()
            if "applied" in btn_text:
                print(f"  ⏭️  Already applied to: {job_title}")
                continue

            print(f"  🎯 Clicking Apply for: {job_title}")
            handles_before = set(driver.window_handles)
            linkedin_tab = driver.current_window_handle
            _retry(lambda: try_click(driver, easy_apply_btn), label=f"Apply btn for '{job_title}'")
            time.sleep(3)

            # Check if an external tab opened first
            ext_result = handle_external_application(driver, config, handles_before, linkedin_tab)

            if ext_result in ("submitted", "filled"):
                applied_count += 1
                label = "submitted" if ext_result == "submitted" else "filled (review & submit)"
                print(f"  📊 External form {label}: {applied_count}/{max_jobs}\n")
            else:
                # No external tab — process LinkedIn Easy Apply modal
                result = process_easy_apply_modal(driver, config)

                if result == "submitted" or result == "closed":
                    applied_count += 1
                    print(f"  📊 Progress: {applied_count}/{max_jobs} applications\n")
                else:
                    print(f"  ⚠️  Could not complete: {job_title}")
                    dismiss_modal(driver)

            # Short delay between applications
            delay = random.uniform(3, 8)
            time.sleep(delay)

        except StaleElementReferenceException:
            print(f"  [Retry] Card went stale, will re-find on next iteration")
            # Don't increment index — it will re-find from same position
        except Exception as e:
            print(f"  ❌ Error on '{job_title}': {type(e).__name__}: {e}")
            dismiss_modal(driver)

    return applied_count


def run(driver, config, applied_count, max_jobs, applied_urls=None):
    """
    Main entry point. Cycles keywords continuously until:
    - max_jobs reached, OR
    - stop event is set (user clicks Stop).

    Each keyword is searched across all locations with pagination.
    After exhausting all keywords, cycles back to keyword 1 to keep applying.
    """
    if applied_urls is None:
        applied_urls = set()
    min_per_kw = config.get("min_per_keyword", 10)
    keyword_stats = {}
    _stop = config.get("_stop_event")  # threading.Event — set when user clicks Stop
    keywords = config.get("keywords", [])
    if not keywords:
        print("[LinkedIn] ⚠️  No keywords configured. Aborting.")
        return applied_count

    cycle = 0
    while True:
        if applied_count >= max_jobs:
            print(f"[LinkedIn] ✅ Reached max_jobs={max_jobs}. Stopping.")
            break
        if _stop and _stop.is_set():
            print("[LinkedIn] 🛑 Stop requested by user — exiting.")
            break

        cycle += 1
        print(f"\n{'═'*60}\n[LinkedIn] 🔄 CYCLE {cycle} — {applied_count}/{max_jobs} applied so far\n{'═'*60}")

        cycle_applied = 0
        for keyword in keywords:
            if applied_count >= max_jobs or (_stop and _stop.is_set()):
                break

            kw_applied = 0
            keyword_stats[keyword] = keyword_stats.get(keyword, 0)

            print(f"\n{'═' * 60}")
            print(f"🎯 KEYWORD: '{keyword}' — Target: {min_per_kw} applications")
            print(f"{'═' * 60}")

            for location in config.get("locations", ["India"]):
                if applied_count >= max_jobs or (_stop and _stop.is_set()):
                    break

                # Paginate through multiple pages of search results
                for page in range(5):  # Up to 5 pages per location
                    if applied_count >= max_jobs or (_stop and _stop.is_set()):
                        break

                    start = page * 25  # LinkedIn uses 25 results per page

                    print(f"\n{'─' * 50}")
                    print(f"🔍 '{keyword}' in '{location}' (page {page + 1})")
                    print(f"   Progress: {kw_applied}/{min_per_kw} for this keyword | {applied_count}/{max_jobs} total")
                    print(f"{'─' * 50}")

                    # ── Build LinkedIn filters from user preferences ──────────────
                    _JT_MAP = {
                        "Full-time": "F", "Internship": "I", "Part-time": "P",
                        "Contract": "C", "Trainee": "I", "Fresher": "I",
                    }
                    employment_types = config.get("employment_types", [])
                    jt_codes = list({_JT_MAP[et] for et in employment_types if et in _JT_MAP})
                    if not jt_codes:
                        kw_lower = keyword.lower()
                        if any(w in kw_lower for w in ("intern", "trainee", "apprentice")):
                            jt_codes = ["I"]
                        else:
                            jt_codes = ["F"]
                    jt_param = "".join(f"&f_JT={c}" for c in jt_codes)

                    has_intern = "I" in jt_codes
                    has_fulltime = any(c in jt_codes for c in ("F", "C", "P"))
                    if has_intern and has_fulltime:
                        fe_param = "&f_E=1%2C2%2C3"
                    elif has_intern:
                        fe_param = "&f_E=1"
                    else:
                        fe_param = "&f_E=2%2C3%2C4"

                    search_url = (
                        f"https://www.linkedin.com/jobs/search/?"
                        f"keywords={keyword.replace(' ', '%20')}"
                        f"&location={location.replace(' ', '%20')}"
                        f"&f_AL=true"
                        f"{fe_param}"
                        f"{jt_param}"
                        f"&f_TPR=r604800"    # last 7 days
                        f"&sortBy=DD"
                        f"&start={start}"
                    )
                    print(f"  [Search] {keyword} | {location} | Types: {employment_types or ['Any']} | URL: ...{jt_param}{fe_param}")

                    driver.get(search_url)
                    time.sleep(5)

                    before = applied_count
                    applied_count = apply_from_search_page(
                        driver, config, applied_count, max_jobs,
                        current_keywords=[keyword]
                    )
                    page_applied = applied_count - before
                    kw_applied += page_applied
                    cycle_applied += page_applied

                    print(f"\n  📊 This page: +{page_applied} | Keyword total: {kw_applied}/{min_per_kw} | Overall: {applied_count}/{max_jobs}")

                    # Only skip remaining pages if two consecutive pages yield 0
                    if page_applied == 0 and page >= 1:
                        print(f"  [Info] Two empty pages — moving to next location.")
                        break

            keyword_stats[keyword] = keyword_stats.get(keyword, 0) + kw_applied
            print(f"\n✅ '{keyword}': Applied to {kw_applied} jobs this cycle")

        # After one full cycle, brief pause then loop again unless stopped
        if _stop and _stop.is_set():
            break
        if applied_count >= max_jobs:
            break
        print(f"\n[LinkedIn] ⏳ Cycle {cycle} complete ({cycle_applied} applied). Looping again in 10s…")
        time.sleep(10)

    print(f"\n{'═' * 60}")
    print(f"[LinkedIn] ✅ SESSION COMPLETE after {cycle} cycle(s)")
    print(f"{'═' * 60}")
    for kw, count in keyword_stats.items():
        print(f"  {'✅' if count > 0 else '⚠️'} {kw}: {count} applications")
    print(f"  📊 Total applied: {applied_count}")
    print(f"{'═' * 60}")

    return applied_count
