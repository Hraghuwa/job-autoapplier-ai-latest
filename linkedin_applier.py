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
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, StaleElementReferenceException,
    ElementNotInteractableException
)
import agent_vision

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

        prompt = f"""You are filling a LinkedIn job application form for Harsh Raghuwanshi.
Read the EXACT question carefully and answer with ONLY the value, nothing else.

Harsh's profile:
- Name: Harsh Raghuwanshi
- MBA at TAPMI Bengaluru (2025-2027), MBA CGPA: 6.97
- BA Programme from Delhi University, Graduation CGPA: 7.80
- 12th marks: 78% | 10th marks: 85%
- Cofounder of Apna Supermarket (4 years, ₹2.5 Cr turnover)
- Skills: Product Management, Python, SQL, Power BI, Figma, AI Tools
- IBM AI Product Manager certified
- Phone: 8109580642, Email: hraghu3110@outlook.com
- Location: Bengaluru, Karnataka, India, Pin: 560001
- Notice period: 20 days, Can join: 01/04/2026
- Expected salary: 40000, Current/Previous salary: 80000
- Years of experience: 4

Form question: "{question}"

CRITICAL RULES — READ CAREFULLY:
- If asking for 10th / SSC / Class X marks → answer "85"
- If asking for 12th / HSC / Class XII marks → answer "78"
- If asking for graduation / UG CGPA → answer "7.80"
- If asking for MBA / PG / current CGPA → answer "6.97"
- If asking for generic "marks" or "percentage" → answer "78" (12th default)
- If asking for generic "CGPA/GPA" → answer "7.80" (graduation default)
- If asking about experience with a tool/skill, answer years (e.g., "4")
- If yes/no question, answer "Yes" if Harsh likely qualifies
- If asking about salary/CTC/stipend, answer "40000"
- If asking about current salary, answer "80000"
- If asking about notice period, answer "20 days"
- If asking about location/city, answer "Bangalore"
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

    if not password or password.startswith("YOUR_"):
        print("[LinkedIn] ❌ Password not set! Update config.py with your real password.")
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
    if "feed" in url or "checkpoint" in url or "mynetwork" in url or "jobs" in url:
        print("[LinkedIn] ✅ Logged in successfully!")
        return True
    elif "challenge" in url or "security" in url:
        print("[LinkedIn] ⚠️  Security challenge detected. Please solve it manually in the browser.")
        print("[LinkedIn] ⏳ Waiting 30 seconds for you to complete the challenge...")
        time.sleep(30)
        return True
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
    field_rules = [
        # ── Name fields ──
        (["first name", "given name"], profile.get("first_name", "Harsh")),
        (["last name", "surname", "family name"], profile.get("last_name", "Raghuwanshi")),
        (["full name", "your name", "candidate name"], profile.get("full_name", "Harsh Raghuwanshi")),

        # ── Contact ──
        (["phone", "mobile", "contact number", "tel", "whatsapp"], profile.get("phone", "8109580642")),
        (["email", "e-mail", "mail id"], profile.get("email", "hraghu3110@outlook.com")),
        (["linkedin", "profile url", "portfolio"], profile.get("linkedin", "")),

        # ── Location ──
        (["city", "current city", "hometown"], profile.get("location", "Bangalore")),
        (["state"], "Karnataka"),
        (["country"], profile.get("country", "India")),
        (["address", "street", "location"], "Bangalore, Karnataka, India"),
        (["pin", "zip", "postal"], "560001"),

        # ── Education marks — SPECIFIC rules first! ──
        # 10th / SSC / Class X
        (["10th", "ssc", "class 10", "class x", "xth", "tenth", "matric"],
         profile.get("tenth_marks", "85")),
        # 12th / HSC / Class XII
        (["12th", "hsc", "class 12", "class xii", "xiith", "twelfth", "inter", "plus two", "+2", "senior secondary"],
         profile.get("twelfth_marks", "78")),
        # MBA / Current CGPA
        (["mba cgpa", "mba gpa", "current cgpa", "pg cgpa", "postgrad"],
         profile.get("mba_cgpa", "6.97")),
        # Graduation / UG CGPA
        (["grad cgpa", "ug cgpa", "undergrad", "bachelor", "btech", "b.tech", "ba ", "bsc", "b.sc", "b.com"],
         profile.get("grad_cgpa", "7.80")),
        # Generic CGPA — graduation by default
        (["cgpa", "gpa"], profile.get("grad_cgpa", "7.80")),
        # Generic percentage — 12th by default (most common ask)
        (["percentage", "percent", "%", "marks", "score", "grade"],
         profile.get("twelfth_marks", "78")),

        # ── Education details ──
        (["university", "college", "school", "institution"], profile.get("university", "TAPMI Bengaluru")),
        (["degree", "qualification", "course"], profile.get("degree", "MBA")),
        (["major", "field of study", "specialization", "branch", "stream"], "Technology Management"),
        (["graduation", "passing year", "end year", "year of completion", "batch"], profile.get("graduation_year", "2027")),
        (["start year", "joining year", "enrollment"], "2025"),

        # ── Experience & duration ──
        (["years of experience", "total experience", "work experience", "relevant experience"],
         profile.get("years_experience", "4")),
        (["duration", "internship period", "period", "how long", "months"], profile.get("internship_duration", "3 months")),
        (["notice period", "joining time", "notice"], profile.get("notice_period", "20")),
        (["current company", "current organization", "employer", "company name"], profile.get("current_company", "Apna Supermarket")),
        (["current role", "current title", "designation", "job title", "position"], profile.get("current_role", "Cofounder")),
        (["available", "availability", "start date", "join date", "earliest"], profile.get("availability", "01/04/2026")),

        # ── Salary & compensation ──
        (["current salary", "current ctc", "present salary", "present ctc", "last drawn"],
         profile.get("previous_salary", "80000")),
        (["expected salary", "expected ctc", "salary expectation"],
         profile.get("expected_salary", "40000")),
        (["salary", "ctc", "compensation", "stipend"], profile.get("expected_salary", "40000")),

        # ── Authorization ──
        (["authorized", "authorization", "legally", "eligible", "visa", "permit"],
         profile.get("legally_authorized", "Yes")),
        (["sponsorship", "sponsor"], profile.get("require_sponsorship", "No")),
        (["relocat", "willing to relocate"], profile.get("willing_to_relocate", "Yes")),
        (["how did you hear", "source", "referral", "where did you"], profile.get("heard_about_us", "LinkedIn")),

        # ── Skills & Certifications ──
        (["skill", "expertise", "competenc", "proficien"], profile.get("skills", "Product Management, Python, SQL, Power BI")),
        (["certif", "credential"], profile.get("certifications", "IBM AI Product Manager")),
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
                    ai_answer = _ask_ai(combined, config)
                    if ai_answer:
                        inp.clear()
                        inp.send_keys(ai_answer)
                        filled_something = True
                        print(f"    [AI] {combined[:40]}: {ai_answer[:30]}")
                    else:
                        inp.clear()
                        inp.send_keys("Yes")
                        filled_something = True
                        print(f"    [Fill] Unknown ({combined[:40]}): Yes")

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

                if any(w in combined for w in ["experience", "year"]):
                    inp.clear()
                    inp.send_keys(profile.get("years_experience", "4"))
                    print(f"    [Fill] Years experience: {profile.get('years_experience', '4')}")
                elif any(w in combined for w in ["gpa", "cgpa", "grade"]):
                    inp.clear()
                    inp.send_keys(profile.get("cgpa", "7.80"))
                    print(f"    [Fill] GPA: {profile.get('cgpa', '7.80')}")
                elif any(w in combined for w in ["salary", "ctc", "stipend"]):
                    inp.clear()
                    inp.send_keys("0")
                    print("    [Fill] Salary: 0")
                else:
                    inp.clear()
                    inp.send_keys("0")
                    print(f"    [Fill] Numeric ({combined[:30]}): 0")
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

    for step in range(max_steps):
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


def _is_title_relevant(job_title, keywords):
    """
    Check if a job title is relevant to the target keywords.
    Relaxed rules for broader matching.
    """
    title_lower = job_title.lower().strip()
    if not title_lower:
        return False

    # ── RULE 1: Entry-level check ──
    intern_terms = ["intern", "trainee", "apprentice", "fellow", "associate", "candidate", "student", "graduate", "fresher"]
    is_entry_level = any(t in title_lower for t in intern_terms)
    
    # ── RULE 2: Blocklist check ──
    blocked_roles = [
        "senior", "lead", "staff", "principal", "architect", "expert", "director", "vp", "manager",
        "sr.", "sr ", "ii", "iii"
    ]
    if any(b in title_lower for b in blocked_roles):
        return False, "Senior/Lead role blocked"

    # ── RULE 3: Target Keywords check ──
    wanted_terms = keywords or ["product", "management", "strategy", "ai", "tech", "business", "analyst"]
    for term in wanted_terms:
        if term.lower() in title_lower:
            return True, f"Matches keyword: {term}"

    # If it's an intern/trainee role but no keywords matched, we might still want to look
    if is_entry_level:
        return True, "Entry-level role (intern/trainee)"

    return False, "No keywords matched"


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

    while card_index < total_count and applied_count < max_jobs:
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
            if not _is_title_relevant(job_title, filter_keywords):
                print(f"  ⏭️  Skipping (not relevant): {job_title}")
                continue

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
            try_click(driver, easy_apply_btn)
            time.sleep(3)

            # Process the Easy Apply modal
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
            print(f"  ❌ Error processing job card: {e}")
            dismiss_modal(driver)

    return applied_count


def run(driver, config, applied_count, max_jobs, applied_urls=None):
    """
    Main entry point. For each keyword:
      1. Try to apply to at least min_per_keyword jobs (default 10)
      2. Search across all locations and paginate to find enough jobs
      3. Move to next keyword once target is reached
    """
    if applied_urls is None:
        applied_urls = set()
    min_per_kw = config.get("min_per_keyword", 10)
    keyword_stats = {}

    for keyword in config["keywords"]:
        if applied_count >= max_jobs:
            break

        kw_applied = 0
        keyword_stats[keyword] = 0

        print(f"\n{'═' * 60}")
        print(f"🎯 KEYWORD: '{keyword}' — Target: {min_per_kw} applications")
        print(f"{'═' * 60}")

        for location in config["locations"]:
            if kw_applied >= min_per_kw or applied_count >= max_jobs:
                break

            # Paginate through multiple pages of search results
            for page in range(5):  # Up to 5 pages per location
                if kw_applied >= min_per_kw or applied_count >= max_jobs:
                    break

                start = page * 25  # LinkedIn uses 25 results per page

                print(f"\n{'─' * 50}")
                print(f"🔍 '{keyword}' in '{location}' (page {page + 1})")
                print(f"   Progress: {kw_applied}/{min_per_kw} for this keyword | {applied_count}/{max_jobs} total")
                print(f"{'─' * 50}")

                search_url = (
                    f"https://www.linkedin.com/jobs/search/?"
                    f"keywords={keyword.replace(' ', '%20')}"
                    f"&location={location.replace(' ', '%20')}"
                    f"&f_AL=true"
                    f"&f_E=1"
                    f"&f_TPR=r86400"
                    f"&sortBy=DD"
                    f"&start={start}"
                )

                driver.get(search_url)
                time.sleep(5)

                before = applied_count
                applied_count = apply_from_search_page(
                    driver, config, applied_count, max_jobs,
                    current_keywords=[keyword]
                )
                page_applied = applied_count - before
                kw_applied += page_applied

                print(f"\n  📊 This page: +{page_applied} | Keyword total: {kw_applied}/{min_per_kw} | Overall: {applied_count}/{max_jobs}")

                # If no jobs were found/applied on this page, skip remaining pages for this location
                if page_applied == 0:
                    print(f"  [Info] No applications on this page, trying next location...")
                    break

        keyword_stats[keyword] = kw_applied
        print(f"\n✅ '{keyword}': Applied to {kw_applied} jobs")

    print(f"\n{'═' * 60}")
    print(f"[LinkedIn] ✅ SESSION COMPLETE")
    print(f"{'═' * 60}")
    for kw, count in keyword_stats.items():
        status = "✅" if count >= min_per_kw else "⚠️"
        print(f"  {status} {kw}: {count}/{min_per_kw}")
    print(f"  📊 Total applied: {applied_count}")
    print(f"{'═' * 60}")

    return applied_count
