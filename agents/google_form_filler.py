"""
📝 Google Form & Web Form Auto-Filler
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detects Google Forms and standard web forms on opened tabs.
Auto-fills fields using profile data and uploads resume.
Works with: Google Forms, Typeform, JotForm, standard HTML forms.
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
    """Match a form field label to the right answer from config."""
    profile = config.get("profile", {})
    c = label.lower()

    # Name
    if any(w in c for w in ["your name", "full name", "candidate name", "name"]):
        return profile.get("full_name", "Harsh Raghuwanshi")

    # LinkedIn
    if any(w in c for w in ["linkedin", "linkedin id", "linkedin url"]):
        return profile.get("linkedin", "https://www.linkedin.com/in/harsh-raghuwanshi-570868359/")

    # Portfolio / Personal Website
    if any(w in c for w in ["portfolio", "website", "personal website", "link to your work"]):
        return profile.get("personal_website", "https://harshraghuwanshi.figma.site")

    # Email
    if any(w in c for w in ["email", "e-mail", "mail id", "email id"]):
        return profile.get("email", "hraghu3110@outlook.com")

    # Phone
    if any(w in c for w in ["phone", "mobile", "contact", "whatsapp"]):
        return profile.get("phone", "8109580642")

    # College
    if any(w in c for w in ["university", "college", "institute", "institution"]):
        return profile.get("college", "Manipal/T.A Pai Management Institute")

    # Course
    if any(w in c for w in ["course", "pursuing", "completed"]):
        return profile.get("course", "MBA")

    # Branch
    if any(w in c for w in ["branch", "specialization", "stream", "department"]):
        return profile.get("branch", "Technology Management")

    # Year of passing
    if any(w in c for w in ["passing", "graduation", "year of"]):
        return profile.get("graduation_year", "2027")

    # CGPA
    if any(w in c for w in ["cgpa", "gpa", "percentage", "marks"]):
        return profile.get("cgpa", "6.97")

    # Current/Last role
    if any(w in c for w in ["current role", "last role", "current/last", "designation"]):
        return profile.get("current_role", "Cofounder")

    # Current stipend/salary
    if any(w in c for w in ["current stipend", "current salary", "current ctc", "present"]):
        return profile.get("current_ctc", "80000")

    # Expected stipend/salary
    if any(w in c for w in ["expected stipend", "expected salary", "expected ctc"]):
        return profile.get("expected_salary", "40000")

    # Location
    if any(w in c for w in ["location", "city", "based", "where"]):
        return profile.get("location", "Bangalore")

    # Join date
    if any(w in c for w in ["earliest", "joining", "join date", "start date", "how soon", "availability"]):
        return profile.get("join_date", "01/04/2026")

    # Notice period
    if any(w in c for w in ["notice period", "notice"]):
        return profile.get("notice_period", "20") + " days"

    # Laptop
    if any(w in c for w in ["laptop"]):
        return "Yes"

    # Tools
    if any(w in c for w in ["tools", "which tools", "tools used"]):
        return profile.get("tools_used", "Google AI Studio, Anti Gravity, Replit, Gemini, Claude")

    # RAG
    if any(w in c for w in ["rag", "retrieval augmented", "retrieval-augmented"]):
        return profile.get("rag_explanation",
            "Sourcing information directly from the origin eliminates hallucinations.")

    # Product/AI experience
    if any(w in c for w in ["product", "startup", "ai-related", "worked on any"]):
        return "Yes"

    # Experience
    if any(w in c for w in ["experience", "years"]):
        return profile.get("years_experience", "4")

    # Why / Motivation
    if any(w in c for w in ["why", "motivation", "interest"]):
        return ("I am passionate about this role. I bring 4+ years of entrepreneurial experience "
                "in product management, GTM strategy, and AI tools from co-founding Apna Supermarket.")

    # Skills
    if any(w in c for w in ["skill", "strength"]):
        return "Product Management, Data Analysis, Python, SQL, AI Tools, Figma"

    return None


# ─────────────────────────────────────────────
#  GOOGLE FORM FILLER
# ─────────────────────────────────────────────
def fill_google_form(driver, config):
    """Auto-fill a Google Form with profile data and upload resume."""
    print("    📝 [GoogleForm] Auto-filling...")
    filled_count = 0
    resume_path = config.get("resume_path", "")

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
                        answer = config.get("cover_letter", "")[:500] if config.get("cover_letter") else (
                            "I am Harsh Raghuwanshi, pursuing MBA at T.A Pai Management Institute. "
                            "I bring 4+ years of entrepreneurial experience as Cofounder of Apna Supermarket.")
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
    resume_path = config.get("resume_path", "")

    # ── ATS-specific direct field mapping by name/id attribute ──
    # Common ATS platforms use predictable name/id values
    ats_field_map = {
        # Name variants
        "first_name": profile.get("first_name", "Harsh"),
        "firstname":  profile.get("first_name", "Harsh"),
        "first-name": profile.get("first_name", "Harsh"),
        "fname":      profile.get("first_name", "Harsh"),
        "last_name":  profile.get("last_name", "Raghuwanshi"),
        "lastname":   profile.get("last_name", "Raghuwanshi"),
        "last-name":  profile.get("last_name", "Raghuwanshi"),
        "lname":      profile.get("last_name", "Raghuwanshi"),
        "full_name":  profile.get("full_name", "Harsh Raghuwanshi"),
        "fullname":   profile.get("full_name", "Harsh Raghuwanshi"),
        "name":       profile.get("full_name", "Harsh Raghuwanshi"),
        "candidate_name": profile.get("full_name", "Harsh Raghuwanshi"),
        # Contact
        "email":      profile.get("email", "hraghu3110@outlook.com"),
        "email_address": profile.get("email", "hraghu3110@outlook.com"),
        "phone":      profile.get("phone", "8109580642"),
        "phone_number": profile.get("phone", "8109580642"),
        "mobile":     profile.get("phone", "8109580642"),
        "mobile_number": profile.get("phone", "8109580642"),
        "contact":    profile.get("phone", "8109580642"),
        # Location
        "city":       profile.get("city", "Bangalore"),
        "location":   profile.get("location", "Bangalore"),
        "address":    "Bangalore, Karnataka, India",
        "pincode":    "560001",
        "zip":        "560001",
        # Social
        "linkedin":   profile.get("linkedin", "https://www.linkedin.com/in/harsh-raghuwanshi-570868359/"),
        "linkedin_url": profile.get("linkedin", "https://www.linkedin.com/in/harsh-raghuwanshi-570868359/"),
        "portfolio":  "https://harshraghuwanshi.figma.site",
        "website":    "https://harshraghuwanshi.figma.site",
        # Education
        "college":    profile.get("college", "TAPMI Bengaluru"),
        "university": profile.get("university", "Manipal/T.A Pai Management Institute"),
        "institution": profile.get("college", "TAPMI Bengaluru"),
        "degree":     profile.get("degree", "MBA"),
        "course":     profile.get("course", "MBA"),
        "branch":     profile.get("branch", "Technology Management"),
        "specialization": profile.get("branch", "Technology Management"),
        "cgpa":       profile.get("cgpa", "7.80"),
        "gpa":        profile.get("cgpa", "7.80"),
        "percentage": profile.get("twelfth_marks", "78"),
        "graduation_year": profile.get("graduation_year", "2027"),
        "passing_year": profile.get("graduation_year", "2027"),
        "year_of_passing": profile.get("graduation_year", "2027"),
        # Experience
        "experience": profile.get("years_experience", "4"),
        "years_of_experience": profile.get("years_experience", "4"),
        "total_experience": profile.get("years_experience", "4"),
        "current_company": profile.get("current_company", "Apna Supermarket"),
        "company":    profile.get("current_company", "Apna Supermarket"),
        "designation": profile.get("current_role", "Cofounder"),
        "current_role": profile.get("current_role", "Cofounder"),
        "notice_period": profile.get("notice_period", "20"),
        "notice":     profile.get("notice_period", "20"),
        # Salary
        "current_ctc": profile.get("current_ctc", "80000"),
        "current_salary": profile.get("current_ctc", "80000"),
        "expected_ctc": profile.get("expected_salary", "40000"),
        "expected_salary": profile.get("expected_salary", "40000"),
        "salary":     profile.get("expected_salary", "40000"),
        "stipend":    profile.get("expected_salary", "40000"),
        # Duration
        "duration":   "3",
        "internship_duration": "3",
        "months":     "3",
        # Skills
        "skills":     profile.get("skills", "Product Management, Python, SQL, Power BI, Figma"),
        "cover_letter": config.get("cover_letter", "")[:500],
        "message":    config.get("cover_letter", "")[:300],
        "about":      config.get("cover_letter", "")[:300],
    }

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
                    answer = config.get("cover_letter", "")[:500] or (
                        "I am Harsh Raghuwanshi, MBA student at TAPMI Bengaluru with 4+ years of "
                        "entrepreneurial experience in product management and AI tools.")

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
        print(f"    ❌ [WebForm] Error: {e}")
        traceback.print_exc()

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
