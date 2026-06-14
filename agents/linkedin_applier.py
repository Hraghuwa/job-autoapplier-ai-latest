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
    """Answer a LinkedIn form question via the unified llm_router.
    Routes Ollama (local) → Groq → Gemini. None on failure."""
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

    try:
        from llm_router import generate
        answer = generate(prompt, role="form_fill", config=config, max_tokens=120, temperature=0.1)
        if answer:
            answer = answer.strip().strip('"').strip("'")
            if answer and len(answer) < 200:
                return answer
    except Exception as e:
        print(f"    [AI Error] {type(e).__name__}: {str(e)[:100]}")

    # Heuristic fallback if every LLM tier failed — generic but safe.
    q = question.lower()
    if "notice period" in q: return config.get("profile", {}).get("notice_period", "30 days")
    if "salary" in q or "ctc" in q: return config.get("profile", {}).get("expected_salary", "0")
    if "experience" in q or "years" in q: return config.get("profile", {}).get("years_of_experience", "1")
    if "authorized" in q or "eligible" in q: return "Yes"
    if "sponsorship" in q: return "No"
    if "relocate" in q: return "Yes"
    return None


def _try_cookie_login(driver, cookies_json: str) -> bool:
    """Inject stored browser cookies → land on /feed/ as logged-in user.

    Uses backend.services.linkedin_cookies.parse_export to:
      - Strip toxic fields (`hostOnly`, `session`, `storeId`, `sameSite=no_restriction`,
        float `expirationDate`) that make Selenium's add_cookie raise.
      - Verify `li_at` is present — the actual auth cookie. Without it,
        injection cannot possibly produce a logged-in session, so we bail
        early instead of wasting a navigation + 5s wait.

    Returns True iff the post-injection navigation lands on a logged-in URL.
    """
    try:
        from backend.services.linkedin_cookies import (
            parse_export, has_valid_session, dump_browser_cookies, extract_li_at,
        )
    except Exception:
        # Fallback: backend services not importable (CLI use). Use the legacy
        # minimal parser inline.
        parse_export = lambda raw: []  # noqa: E731
        has_valid_session = lambda c: False  # noqa: E731
        dump_browser_cookies = lambda d: "[]"  # noqa: E731
        extract_li_at = lambda c: None  # noqa: E731

    cookies = parse_export(cookies_json or "")
    if not cookies:
        print("[LinkedIn] ⚠️  Could not parse cookies JSON.")
        return False
    if not has_valid_session(cookies):
        print("[LinkedIn] ⚠️  No li_at cookie present — session is not authenticated. "
              "Re-export AFTER logging in to linkedin.com.")
        return False

    try:
        # Be on the right domain before add_cookie or Chrome rejects the host.
        driver.get("https://www.linkedin.com")
        time.sleep(2)

        injected = 0
        rejected_reasons: dict = {}
        for c in cookies:
            try:
                driver.add_cookie(c)
                injected += 1
            except Exception as e:
                key = type(e).__name__
                rejected_reasons[key] = rejected_reasons.get(key, 0) + 1
        if rejected_reasons:
            print(f"[LinkedIn] 🍪 {injected} cookies accepted; rejected: {rejected_reasons}")

        if injected == 0:
            print("[LinkedIn] ⚠️  No cookies could be injected.")
            return False

        driver.get("https://www.linkedin.com/feed/")
        time.sleep(5)

        url = driver.current_url
        if any(x in url for x in ("feed", "mynetwork", "jobs")):
            print(f"[LinkedIn] ✅ Cookie login successful! Session active "
                  f"(li_at={extract_li_at(cookies)[:8] if extract_li_at(cookies) else '?'}...).")
            # Persist refreshed cookies — LinkedIn rotates session tokens
            # on every authenticated load. Saving here keeps the agent
            # working tomorrow without the user re-exporting.
            try:
                from config import CONFIG
                cb = CONFIG.get("_save_linkedin_cookies")
                if callable(cb):
                    fresh = dump_browser_cookies(driver)
                    if fresh and fresh != "[]":
                        cb(fresh)
            except Exception:
                pass
            return True

        print(f"[LinkedIn] ℹ️  Cookies did not establish a valid session (URL: {url}). "
              f"They may be expired — re-export from your logged-in browser.")
        return False
    except Exception as e:
        print(f"[LinkedIn] ⚠️  Cookie injection error: {type(e).__name__}: {e}")
        return False


def login(driver, email, password, cookies_json: str = None):
    print("\n[LinkedIn] 🔐 Initializing login...")

    # ── 1. Try cookie injection first (bypasses CAPTCHA/security challenges) ──
    if not cookies_json:
        try:
            from config import CONFIG
            cookies_json = CONFIG.get("linkedin_cookies", "")
        except Exception:
            pass

    if cookies_json:
        print("[LinkedIn] 🍪 Attempting cookie-based login...")
        if _try_cookie_login(driver, cookies_json):
            return True
        print("[LinkedIn] ℹ️  Cookie login failed — falling back to password login.")

    # ── 2. Password login ─────────────────────────────────────────────────────
    if not email or not password or password.startswith("YOUR_"):
        print("[LinkedIn] ❌ Credentials not set! Add them in the Credentials page.")
        return False

    driver.get("https://www.linkedin.com/login")
    time.sleep(3)

    try:
        # LinkedIn rotates between stable IDs and generated React IDs.
        # Prefer stable selectors, then fall back to visible email/password inputs.
        email_field = None
        pass_field = None
        for by, sel in [
            (By.ID, "username"),
            (By.ID, "session_key"),
            (By.CSS_SELECTOR, "input[name='session_key']"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[autocomplete='username']"),
        ]:
            try:
                candidates = driver.find_elements(by, sel)
                email_field = next((el for el in candidates if el.is_displayed()), None)
                if email_field:
                    break
            except Exception:
                continue
        for by, sel in [
            (By.ID, "password"),
            (By.ID, "session_password"),
            (By.CSS_SELECTOR, "input[name='session_password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
        ]:
            try:
                candidates = driver.find_elements(by, sel)
                pass_field = next((el for el in candidates if el.is_displayed()), None)
                if pass_field:
                    break
            except Exception:
                continue
        if not email_field or not pass_field:
            raise TimeoutException("LinkedIn login form fields were not visible.")

        email_field.clear()
        email_field.send_keys(email)

        pass_field.clear()
        pass_field.send_keys(password)

        submitted = False
        buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button")
        submit = next(
            (b for b in buttons if b.is_displayed() and (
                b.get_attribute("type") == "submit" or "sign in" in b.text.lower()
            )),
            None,
        )
        if submit:
            try:
                submit.click()
                submitted = True
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", submit)
                    submitted = True
                except Exception:
                    pass
        if not submitted:
            pass_field.send_keys(Keys.RETURN)
            
        print("[LinkedIn] Submitted login form, waiting for response...")
        time.sleep(10)

        if "login" in driver.current_url:
            try:
                pass_field.send_keys(Keys.RETURN)
                time.sleep(5)
            except Exception:
                pass
    except Exception as e:
        print(f"[LinkedIn] ❌ Login error: {e}")
        return False

    url = driver.current_url
    if "feed" in url or "mynetwork" in url or "jobs" in url:
        print("[LinkedIn] ✅ Logged in successfully!")
        return True
    elif "checkpoint" in url or "challenge" in url or "security" in url:
        # Check if we're running headless (server context) — can't solve CAPTCHA headlessly
        headless = False
        try:
            from config import CONFIG
            headless = CONFIG.get("headless", False)
        except Exception:
            pass

        if headless:
            print("[LinkedIn] ❌ Security challenge detected in headless mode.")
            print("[LinkedIn] ℹ️  Fix: Go to Credentials page → 'LinkedIn Login Boost' → export cookies from your browser and paste them.")
            print("[LinkedIn]    The agent will use your session cookies to bypass this challenge next time.")
            return False

        # Non-headless (CLI): give the user time to solve the challenge manually
        print("[LinkedIn] ⚠️  Security challenge detected. Please solve it manually in the browser.")
        print("[LinkedIn] ⏳ Waiting 60 seconds for you to complete the challenge...")
        time.sleep(60)
        url = driver.current_url
        if "feed" in url or "mynetwork" in url or "jobs" in url:
            print("[LinkedIn] ✅ Challenge solved! Logged in successfully.")
            # Snapshot the cookies we just earned so the next run skips
            # password+CAPTCHA entirely.
            try:
                from backend.services.linkedin_cookies import dump_browser_cookies
                from config import CONFIG
                cb = CONFIG.get("_save_linkedin_cookies")
                if callable(cb):
                    cb(dump_browser_cookies(driver))
                    print("[LinkedIn] 🍪 Saved fresh session cookies for next run.")
            except Exception:
                pass
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
                    try:
                        from backend.services.cover_note import resolve_cover_note
                        _ln_note = resolve_cover_note(config)
                    except Exception:
                        _ln_note = config.get("cover_letter", "")
                    ta.send_keys(_ln_note or
                        "I am excited to apply for this opportunity and believe my skills align well with the role.")
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


def _find_modal(driver):
    """
    Locate the LinkedIn Easy Apply modal using multiple selector strategies.
    Returns the modal element or None.
    LinkedIn frequently renames classes so we try many variants.
    """
    MODAL_SELECTORS = [
        "div.jobs-easy-apply-modal",
        "div.artdeco-modal--is-open",
        "div.artdeco-modal",
        "div[role='dialog']",
        "[aria-modal='true']",
        "div[data-test-modal]",
        "div.jobs-easy-apply-content",
        "div.jobs-apply-flow",
    ]
    for sel in MODAL_SELECTORS:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    return el
        except Exception:
            pass
    return None


def _find_modal_action_button(driver):
    """
    Find the primary action button (Next / Review / Submit) in the Easy Apply modal.
    Uses a multi-strategy approach resilient to LinkedIn's frequent HTML changes:
      1. aria-label exact matches for known LinkedIn button labels
      2. Button text matches (Next, Review, Submit application)
      3. artdeco-button--primary class (the styled primary button)
      4. Nuclear: last visible button in the modal footer
    Returns (button_element, action_type) or (None, None).
    """
    # Strategy 1: aria-label based (most stable across LinkedIn UI changes)
    ARIA_SUBMIT = ["submit application", "submit"]
    ARIA_NEXT   = ["continue to next step", "next", "review your application", "review"]

    # Strategy 2: button text based
    TEXT_SUBMIT = ["submit application", "submit"]
    TEXT_NEXT   = ["review", "next", "continue"]

    def _check(btn):
        if not btn.is_displayed():
            return None
        text = (btn.text or "").strip().lower()
        aria = (btn.get_attribute("aria-label") or "").strip().lower()
        combined = f"{text} {aria}"
        if any(s in combined for s in ARIA_SUBMIT + TEXT_SUBMIT):
            return "submit"
        if any(s in combined for s in ARIA_NEXT + TEXT_NEXT):
            return "next"
        return None

    # Collect buttons from as many modal containers as possible
    candidates = []
    for sel in [
        "div.jobs-easy-apply-modal button",
        "div.artdeco-modal button",
        "div[role='dialog'] button",
        "[aria-modal='true'] button",
        "div[data-test-modal] button",
        "div.jobs-easy-apply-content button",
        # footer-specific (LinkedIn wraps actions in a footer)
        "footer button",
        "div.jobs-easy-apply-footer button",
        "div.ph5.pb4 button",
        # Direct primary button class (most reliable selector)
        "button.artdeco-button--primary",
        "button[data-easy-apply-next-button]",
    ]:
        try:
            found = driver.find_elements(By.CSS_SELECTOR, sel)
            candidates.extend(found)
        except Exception:
            pass

    # Deduplicate by id() while preserving order
    seen = set()
    unique = []
    for b in candidates:
        bid = id(b)
        if bid not in seen:
            seen.add(bid)
            unique.append(b)

    # Prefer submit over next
    submit_btn = None
    next_btn   = None
    for btn in unique:
        try:
            action = _check(btn)
            if action == "submit" and submit_btn is None:
                submit_btn = btn
            elif action == "next" and next_btn is None:
                next_btn = btn
        except Exception:
            pass

    if submit_btn:
        return submit_btn, "submit"
    if next_btn:
        return next_btn, "next"

    # Nuclear fallback: last visible artdeco-button--primary anywhere on page
    try:
        primary_btns = driver.find_elements(By.CSS_SELECTOR, "button.artdeco-button--primary")
        for btn in reversed(primary_btns):
            if btn.is_displayed():
                return btn, "next"
    except Exception:
        pass

    return None, None


def process_easy_apply_modal(driver, config, dry_run=False):
    """Walk through the multi-step Easy Apply modal until submitted."""
    max_steps = 15
    _stop = config.get("_stop_event")

    for step in range(max_steps):
        if _stop and _stop.is_set():
            print("    [Modal] 🛑 Stop requested — leaving modal open.")
            return "stopped"
        time.sleep(2)

        # Check if modal is still open — use resilient multi-selector helper
        modal = _find_modal(driver)
        if not modal:
            print("    [Modal] Modal closed (may have been one-click apply)")
            return "closed"

        # Check for success message (application already submitted)
        try:
            success = driver.find_elements(By.XPATH,
                "//*[contains(text(),'Application submitted') or "
                "contains(text(),'application was sent') or "
                "contains(text(),'You applied')]")
            if any(s.is_displayed() for s in success):
                print("    ✅ SUCCESS: Application submitted!")
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
            # Phase E: resolve to JD-tailored PDF if possible.
            try:
                from backend.services.resume_resolver import resolve_resume_path
                jd_text = config.get("current_jd_text") or ""
                _resume_to_upload = resolve_resume_path(config, jd_text=jd_text)
            except Exception:
                _resume_to_upload = config.get("resume_path", "")
            upload_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            for upload_input in upload_inputs:
                try:
                    driver.execute_script(
                        "arguments[0].style.display='block'; arguments[0].style.opacity='1';",
                        upload_input)
                    upload_input.send_keys(_resume_to_upload or config["resume_path"])
                    print("    [Resume] Uploaded")
                    time.sleep(2)
                except:
                    pass
        except:
            pass

        # Fill any empty form fields
        fill_modal_fields(driver, config)

        # Find and click the primary action button using the resilient helper
        action_btn, action_type = _find_modal_action_button(driver)
        clicked = False

        if action_btn:
            btn_text  = (action_btn.text or "").strip()
            aria_label = action_btn.get_attribute("aria-label") or ""
            print(f"    🚀 [Step {step+1}] ACTION: Clicking '{btn_text}' ({action_type})")
            try_click(driver, action_btn)
            time.sleep(2)
            clicked = True

            if action_type == "submit":
                if dry_run:
                    print("    🔍 [DRY RUN] Would submit — dismissing modal.")
                    try:
                        dismiss = driver.find_element(By.CSS_SELECTOR,
                            "button[aria-label='Dismiss'], button.artdeco-modal__dismiss")
                        try_click(driver, dismiss)
                        time.sleep(1)
                        discard = driver.find_elements(By.XPATH, "//button[contains(.,'Discard')]")
                        for d in discard:
                            try_click(driver, d)
                    except Exception:
                        pass
                    return "submitted"
                print("    ✅ SUCCESS: Application sent!")
                time.sleep(2)
                # Dismiss success dialog if present
                try:
                    dismiss = driver.find_element(
                        By.XPATH, "//button[contains(@aria-label,'Dismiss')]")
                    try_click(driver, dismiss)
                except Exception:
                    pass
                return "submitted"

        if not clicked:
            # Debug: show all visible buttons so we can diagnose
            print(f"    [Step {step+1}] ⚠️  No action button found — visible buttons on page:")
            try:
                all_btns = driver.find_elements(By.TAG_NAME, "button")
                shown = 0
                for b in all_btns:
                    try:
                        if b.is_displayed() and shown < 8:
                            print(f"      [Debug] '{b.text.strip()[:50]}' aria='{(b.get_attribute('aria-label') or '')[:50]}'")
                            shown += 1
                    except Exception:
                        pass
            except Exception:
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


def apply_from_search_page(driver, config, applied_count, max_jobs, current_keywords=None, dry_run=False):
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
    print(f"  🔍 Scanning page: Found {total_count} matching job cards")

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

            print(f"\n  [{processed}/{total_count}] 🔍 ANALYZING: {job_title}")

            # ── Title relevance filter ──
            filter_keywords = current_keywords or config.get("keywords", [])
            is_relevant, reason = _is_title_relevant(job_title, filter_keywords, config)
            if not is_relevant:
                print(f"  ⏭️  Skipped: {job_title} ({reason})")
                continue

            # ── Extract full JD text and store for tailored resume (Phase E) ──
            try:
                _jd_selectors = [
                    "div.jobs-description-content__text",
                    "div.jobs-description__container",
                    "div#job-details",
                    "div.jobs-description",
                    "article.jobs-description__container",
                ]
                _jd_text = ""
                for _sel in _jd_selectors:
                    try:
                        _el = driver.find_element(By.CSS_SELECTOR, _sel)
                        _jd_text = _el.text.strip()
                        if _jd_text:
                            break
                    except Exception:
                        continue
                config["current_jd_text"] = _jd_text
            except Exception:
                config["current_jd_text"] = ""

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

            # ── Fit gate: think before spending an application (PLAN match gate) ──
            # We have the JD text + title here, just before clicking Apply. Skip
            # jobs the candidate can't win (low must-have coverage) or shouldn't
            # take (unpaid/scam red flags) — saves the daily-apply budget, LLM
            # tailoring cost, and ban-risk. Fail-open: any error → apply as before.
            try:
                from backend.services.apply_decision import should_apply
                _decision = should_apply(config, jd_text=config.get("current_jd_text"),
                                         title=job_title)
                if not _decision.apply:
                    print(f"  ⏭️  Skipping (fit {_decision.score}/100): {_decision.reasons[-1]}")
                    continue
                # Applying — tailor the cover note once for this job (fail-open).
                try:
                    from backend.services.cover_note import generate as _gen_note
                    _note = _gen_note(config.get("profile") or {},
                                      jd_text=config.get("current_jd_text"), config=config)
                    if _note:
                        config["_tailored_cover_note"] = _note
                except Exception:
                    pass
            except Exception:
                pass  # gate must never block a working apply

            # Look for Easy Apply button in the right panel / detail area
            easy_apply_btn = None

            # Strategy 1 — scoped to the job detail panel, most specific first
            DETAIL_PANELS = [
                "div.jobs-details",
                "div.job-details-jobs-unified-top-card",
                "div.jobs-unified-top-card",
                "div.jobs-s-apply",
                "div.job-details",
            ]
            for panel_sel in DETAIL_PANELS:
                if easy_apply_btn:
                    break
                try:
                    panel = driver.find_element(By.CSS_SELECTOR, panel_sel)
                    # Look for Easy Apply class button first
                    for btn in panel.find_elements(By.CSS_SELECTOR, "button.jobs-apply-button"):
                        if btn.is_displayed() and btn.is_enabled():
                            easy_apply_btn = btn
                            break
                    if easy_apply_btn:
                        break
                    # Text / aria-label match within the panel
                    for btn in panel.find_elements(By.TAG_NAME, "button"):
                        if not btn.is_displayed() or not btn.is_enabled():
                            continue
                        txt = btn.text.strip()
                        aria = btn.get_attribute("aria-label") or ""
                        if "Easy Apply" in txt or "Easy Apply" in aria:
                            easy_apply_btn = btn
                            break
                        # Regular external Apply button (opens new tab)
                        if "Apply" in txt and "Applied" not in txt:
                            easy_apply_btn = btn
                            break
                except Exception:
                    continue

            # Strategy 2 — page-wide fallback (scoped XPaths)
            if not easy_apply_btn:
                FALLBACK_XPATHS = [
                    "//button[contains(@class,'jobs-apply-button')]",
                    "//button[contains(normalize-space(),'Easy Apply')]",
                    "//button[contains(@aria-label,'Easy Apply')]",
                    "//button[contains(@aria-label,'Apply') and not(contains(@aria-label,'Applied'))]",
                ]
                for sel in FALLBACK_XPATHS:
                    try:
                        btns = driver.find_elements(By.XPATH, sel)
                        for btn in btns:
                            if btn.is_displayed() and btn.is_enabled():
                                if "Applied" not in (btn.text or ""):
                                    easy_apply_btn = btn
                                    break
                        if easy_apply_btn:
                            break
                    except Exception:
                        continue

            if not easy_apply_btn:
                # Last resort: wait a bit longer and retry the most reliable selector
                time.sleep(3)
                try:
                    easy_apply_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH,
                             "//button[contains(@class,'jobs-apply-button') or "
                             "contains(normalize-space(),'Easy Apply')]")
                        )
                    )
                except Exception:
                    pass

            if not easy_apply_btn:
                print(f"  ⏭️  No Apply button found for: {job_title}")
                continue

            # Check if it says "Applied" (already applied)
            btn_text = easy_apply_btn.text.strip().lower()
            if "applied" in btn_text:
                print(f"  ⏭️  Already applied to: {job_title}")
                continue

            print(f"  🚀 APPLYING: {job_title}...")
            handles_before = set(driver.window_handles)
            linkedin_tab = driver.current_window_handle
            _retry(lambda: try_click(driver, easy_apply_btn), label=f"Apply btn for '{job_title}'")
            time.sleep(3)

            # Check if an external tab opened first
            ext_result = handle_external_application(driver, config, handles_before, linkedin_tab)

            # ── Rate limiter check (prevents account bans) ───────────────────
            try:
                from backend.services.rate_limits import default_limiter
                _uid = str(config.get("user_id", ""))
                _ok, _reason = default_limiter.can_apply(_uid, "linkedin", total_cap=config.get("plan_apply_limit"))
                if not _ok:
                    print(f"  🛑 Rate limit reached: {_reason}")
                    return applied_count
            except Exception:
                pass  # limiter unavailable — proceed without it

            if ext_result in ("submitted", "filled"):
                applied_count += 1
                label = "submitted" if ext_result == "submitted" else "filled (review & submit)"
                print(f"  📊 External form {label}: {applied_count}/{max_jobs}\n")
                try:
                    from backend.services.rate_limits import default_limiter
                    _uid2 = str(config.get("user_id", ""))
                    default_limiter.register_apply(_uid2, "linkedin")
                    default_limiter.register_success(_uid2, "linkedin")  # reset consecutive-failure counter
                except Exception:
                    pass
            else:
                # No external tab — process LinkedIn Easy Apply modal
                result = process_easy_apply_modal(driver, config, dry_run=dry_run)

                if result == "submitted" or result == "closed":
                    applied_count += 1
                    print(f"  📊 Progress: {applied_count}/{max_jobs} applications\n")
                    try:
                        from backend.services.rate_limits import default_limiter
                        _uid2 = str(config.get("user_id", ""))
                        default_limiter.register_apply(_uid2, "linkedin")
                        default_limiter.register_success(_uid2, "linkedin")  # reset consecutive-failure counter
                    except Exception:
                        pass
                else:
                    print(f"  ⚠️  Could not complete: {job_title}")
                    dismiss_modal(driver)
                    try:
                        from backend.services.rate_limits import default_limiter
                        default_limiter.register_failure(str(config.get("user_id", "")), "linkedin")
                    except Exception:
                        pass

            # Adaptive delay between applications — escalates after consecutive
            # failures to dodge bot detection. Fail-open to a flat jittered wait.
            try:
                from backend.services.backoff import delay_for
                delay_for(config, "linkedin")
            except Exception:
                time.sleep(random.uniform(3, 8))

        except StaleElementReferenceException:
            print(f"  [Retry] Card went stale, will re-find on next iteration")
            # Don't increment index — it will re-find from same position
        except Exception as e:
            print(f"  ❌ Error on '{job_title}': {type(e).__name__}: {e}")
            dismiss_modal(driver)

    return applied_count


def run(driver, config, applied_count, max_jobs, applied_urls=None, dry_run=False):
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
                        current_keywords=[keyword], dry_run=dry_run
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
