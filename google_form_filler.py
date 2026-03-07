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
        text_inputs = driver.find_elements(By.CSS_SELECTOR,
            "input[type='text'], input[type='email'], input[type='url'], "
            "input[type='tel'], input:not([type])")

        for inp in text_inputs:
            try:
                if not inp.is_displayed():
                    continue
                val = (inp.get_attribute("value") or "").strip()
                if val:
                    continue

                label = get_form_field_label(driver, inp)
                if not label:
                    continue

                answer = match_answer(label, config)
                if answer:
                    inp.clear()
                    inp.send_keys(str(answer))
                    filled_count += 1
                    print(f"      ✏️  {label[:40]}: {str(answer)[:40]}")
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue

        # ── Fill textareas ──
        textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
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
                    answer = config.get("cover_letter", "")[:500] if config.get("cover_letter") else (
                        "I am Harsh Raghuwanshi, pursuing MBA at T.A Pai Management Institute. "
                        "I bring 4+ years of entrepreneurial experience as Cofounder of Apna Supermarket.")

                ta.clear()
                ta.send_keys(str(answer))
                filled_count += 1
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
def fill_web_form(driver, config):
    """Auto-fill standard HTML forms (Typeform, JotForm, career pages)."""
    print("    📝 [WebForm] Auto-filling...")
    filled_count = 0
    resume_path = config.get("resume_path", "")

    try:
        time.sleep(1)

        # Fill text inputs
        inputs = driver.find_elements(By.CSS_SELECTOR,
            "input[type='text'], input[type='email'], input[type='tel'], "
            "input[type='url'], input[type='number'], input:not([type])")

        for inp in inputs:
            try:
                if not inp.is_displayed():
                    continue
                val = (inp.get_attribute("value") or "").strip()
                if val:
                    continue

                label = get_form_field_label(driver, inp)
                if not label:
                    continue

                answer = match_answer(label, config)
                if answer:
                    inp.clear()
                    inp.send_keys(str(answer))
                    filled_count += 1
                    print(f"      ✏️  {label[:40]}: {str(answer)[:40]}")
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue

        # Fill textareas
        textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
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
                    answer = config.get("cover_letter", "I am Harsh Raghuwanshi...")[:500]

                ta.clear()
                ta.send_keys(str(answer))
                filled_count += 1
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue

        # Upload resume to file inputs
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
            except Exception:
                pass

        print(f"    ✅ [WebForm] Filled {filled_count} fields")

    except Exception as e:
        print(f"    ❌ [WebForm] Error: {e}")

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
