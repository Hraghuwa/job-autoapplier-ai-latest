"""
🧠 Smart Form Filler — Universal Form Auto-Fill Module
Works across ALL job platforms by matching field labels/placeholders
against profile data from config.
"""

import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import (
    NoSuchElementException, StaleElementReferenceException,
    ElementNotInteractableException, ElementClickInterceptedException
)


def try_click(driver, element):
    """Try multiple methods to click an element."""
    try:
        element.click()
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        pass
    return False


def _get_field_label(driver, element):
    """Extract the label/context for a form field from all available sources."""
    parts = []

    # 1. Explicit <label for="id">
    inp_id = element.get_attribute("id") or ""
    if inp_id:
        try:
            label_el = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
            parts.append(label_el.text)
        except NoSuchElementException:
            pass

    # 2. aria-label
    aria = element.get_attribute("aria-label") or ""
    if aria:
        parts.append(aria)

    # 3. placeholder
    placeholder = element.get_attribute("placeholder") or ""
    if placeholder:
        parts.append(placeholder)

    # 4. name attribute
    name = element.get_attribute("name") or ""
    if name:
        parts.append(name.replace("_", " ").replace("-", " "))

    # 5. Ancestor label text
    try:
        parent_label = element.find_element(By.XPATH, "./ancestor::label")
        parts.append(parent_label.text)
    except:
        pass

    # 6. Preceding label / sibling text
    try:
        prev = element.find_element(By.XPATH,
            "./preceding-sibling::label | ./preceding::label[1] | "
            "./ancestor::div[1]//label | ./ancestor::fieldset//legend")
        parts.append(prev.text)
    except:
        pass

    # 7. Parent div text (for label-less forms)
    try:
        parent_div = element.find_element(By.XPATH, "./ancestor::div[1]")
        div_text = parent_div.text.split("\n")[0]  # first line only
        if len(div_text) < 100:
            parts.append(div_text)
    except:
        pass

    # 8. ID itself
    if inp_id:
        parts.append(inp_id.replace("_", " ").replace("-", " "))

    combined = " ".join(parts).lower().strip()
    return combined


def _build_field_rules(config):
    """Build matching rules from config profile data."""
    profile = config.get("profile", {})

    return [
        # Name fields
        (["first name", "given name", "fname", "first_name"], profile.get("first_name", "Harsh")),
        (["last name", "surname", "family name", "lname", "last_name"], profile.get("last_name", "Raghuwanshi")),
        (["full name", "your name", "candidate name", "applicant name", "fullname"], profile.get("full_name", "Harsh Raghuwanshi")),
        (["name"], profile.get("full_name", "Harsh Raghuwanshi")),

        # Contact
        (["phone", "mobile", "contact number", "contact no", "tel", "whatsapp"], profile.get("phone", "8109580642")),
        (["email", "e-mail", "mail id", "mail", "email id"], profile.get("email", "hraghu3110@outlook.com")),
        (["linkedin", "linkedin id", "linkedin url", "profile url"], profile.get("linkedin", "https://www.linkedin.com/in/harsh-raghuwanshi-570868359/")),
        (["portfolio", "website", "personal website", "github", "link to your work"], profile.get("personal_website", "https://harshraghuwanshi.figma.site")),

        # Location
        (["city", "current city", "hometown", "town", "current location"], profile.get("city", "Bangalore")),
        (["location", "address", "place", "based", "currently based"], profile.get("location", "Bangalore")),
        (["street", "address line"], "Bengaluru, Karnataka, India"),
        (["country", "nationality"], profile.get("country", "India")),
        (["state", "province"], "Karnataka"),
        (["pin", "zip", "postal"], "560001"),

        # Education
        (["university", "college", "school", "institution", "institute", "name of your college", "college name"], profile.get("college", "Manipal/T.A Pai Management Institute")),
        (["course", "what course", "pursuing", "completed"], profile.get("course", "MBA")),
        (["degree", "qualification", "program"], profile.get("degree", "MBA")),
        (["branch", "department", "stream", "specialization", "mention your branch"], profile.get("branch", "Technology Management")),
        (["major", "field of study"], "Technology Management"),
        (["gpa", "cgpa", "percentage", "grade", "score", "marks"], profile.get("cgpa", "6.97")),
        (["graduation", "passing year", "year of passing", "end year", "year of completion", "completion year", "batch"], profile.get("graduation_year", "2027")),
        (["start year", "joining year", "admission year"], "2025"),

        # Experience & Work
        (["years of experience", "total experience", "work experience", "exp", "years of professional", "years of relevant"], profile.get("years_experience", "4")),
        (["duration", "internship period", "how long", "tenure"], profile.get("internship_duration", "3 months")),
        (["notice period", "notice"], profile.get("notice_period", "20") + " days"),
        (["how soon", "when can you join", "join date", "start date", "joining date", "date of joining", "available from", "availability", "earliest date"], profile.get("join_date", "01/04/2026")),
        (["current company", "current organization", "employer", "company name", "organisation"], profile.get("current_company", "Apna Supermarket")),
        (["current role", "current title", "last role", "current/last role", "designation", "job title"], profile.get("current_role", "Cofounder")),

        # Salary / Stipend
        (["expected salary", "expected compensation", "expected ctc", "salary expectation", "expected stipend"], profile.get("expected_salary", "40000")),
        (["current salary", "current ctc", "current compensation", "previous salary", "last drawn", "present salary", "present ctc", "current stipend"], profile.get("current_ctc", "80000")),
        (["salary", "ctc", "compensation", "stipend"], profile.get("expected_salary", "40000")),

        # Laptop
        (["laptop", "do you have a laptop"], profile.get("has_laptop", "Yes")),

        # AI / Product experience
        (["tools have you used", "which tools", "tools used"], profile.get("tools_used", "Google AI Studio, Anti Gravity, Replit, Gemini, Claude")),
        (["rag", "retrieval augmented", "retrieval-augmented"], profile.get("rag_explanation", "Sourcing information directly from the origin eliminates hallucinations.")),
        (["product", "startup", "ai-related project", "ai related", "worked on any product"], profile.get("has_product_ai_experience", "Yes")),

        # Authorization / eligibility
        (["authorized", "authorization", "legally", "eligible", "visa", "permit", "right to work"], profile.get("legally_authorized", "Yes")),
        (["sponsorship", "sponsor", "work permit"], profile.get("require_sponsorship", "No")),
        (["relocat", "willing to relocate", "relocation"], profile.get("willing_to_relocate", "Yes")),
        (["how did you hear", "source", "referral", "where did you find"], profile.get("heard_about_us", "LinkedIn")),

        # Skills
        (["skill", "expertise", "competenc", "technologies", "tech stack"], profile.get("skills", "")),
        (["tools", "software", "platforms"], profile.get("tools", "")),
        (["certif", "certificate"], profile.get("certifications", "")),

        # Gender / DOB
        (["gender", "sex"], profile.get("gender", "Male")),
        (["age", "date of birth", "dob", "birth"], profile.get("age", "24")),
    ]


def _smart_text_answer(combined, config):
    """
    Analyze what a text field is asking and return a logical answer.
    Uses context from the field label instead of blindly returning 'Yes'.
    """
    profile = config.get("profile", {})
    c = combined.lower()

    # ── LinkedIn ──
    if any(w in c for w in ["linkedin", "linkedin id", "linkedin url"]):
        return profile.get("linkedin", "https://www.linkedin.com/in/harsh-raghuwanshi-570868359/")

    # ── Email ──
    if any(w in c for w in ["email", "e-mail", "mail id", "email id"]):
        return profile.get("email", "hraghu3110@outlook.com")

    # ── Phone ──
    if any(w in c for w in ["phone", "mobile", "contact no", "contact number", "whatsapp"]):
        return profile.get("phone", "8109580642")

    # ── CGPA ──
    if any(w in c for w in ["cgpa", "gpa", "percentage", "marks", "score"]):
        return profile.get("cgpa", "6.97")

    # ── Motivation / Why questions ──
    if any(w in c for w in ["why do you want", "why are you", "motivation", "interest in",
                             "why this", "why should we", "what excites"]):
        return ("I am passionate about this role and believe my experience in product management, "
                "data analysis, and AI tools will add value. As a co-founder of a retail business, "
                "I have hands-on experience in growth strategy, product roadmapping, and market research.")

    # ── Where did you hear about us ──
    if any(w in c for w in ["how did you hear", "where did you find", "source", "referral",
                             "how did you learn", "how did you know"]):
        return profile.get("heard_about_us", "LinkedIn")

    # ── Join date / Availability / Start date ──
    if any(w in c for w in ["how soon", "when can you join", "start date", "join date",
                             "joining date", "date of joining", "available from",
                             "earliest", "availability", "earliest date"]):
        return profile.get("join_date", "01/04/2026")

    # ── Notice period ──
    if any(w in c for w in ["notice period", "notice"]):
        return profile.get("notice_period", "20") + " days"

    # ── Duration / How long ──
    if any(w in c for w in ["duration", "how long", "tenure"]):
        return profile.get("internship_duration", "3 months")

    # ── Current / Previous Salary / Stipend ──
    if any(w in c for w in ["current salary", "current ctc", "current compensation",
                             "previous salary", "last drawn", "present salary",
                             "present ctc", "current stipend"]):
        return profile.get("current_ctc", "80000")

    # ── Expected Salary / Stipend ──
    if any(w in c for w in ["expected salary", "expected ctc", "salary expectation",
                             "expected compensation", "expected stipend"]):
        return profile.get("expected_salary", "40000")

    # ── Generic salary fallback ──
    if any(w in c for w in ["salary", "ctc", "compensation", "stipend"]):
        return profile.get("expected_salary", "40000")

    # ── Experience ──
    if any(w in c for w in ["years of experience", "total experience", "work experience",
                             "years of professional", "years of relevant"]):
        return profile.get("years_experience", "4")

    # ── Current/Last role ──
    if any(w in c for w in ["current role", "current title", "last role",
                             "current/last role", "designation"]):
        return profile.get("current_role", "Cofounder")

    # ── Laptop ──
    if any(w in c for w in ["laptop", "do you have a laptop"]):
        return profile.get("has_laptop", "Yes")

    # ── RAG explanation ──
    if any(w in c for w in ["rag", "retrieval augmented", "retrieval-augmented"]):
        return profile.get("rag_explanation", "Sourcing information directly from the origin eliminates hallucinations.")

    # ── Tools used ──
    if any(w in c for w in ["tools have you used", "which tools", "tools used"]):
        return profile.get("tools_used", "Google AI Studio, Anti Gravity, Replit, Gemini, Claude")

    # ── Product/AI experience ──
    if any(w in c for w in ["product", "startup", "ai-related project", "worked on any"]):
        return profile.get("has_product_ai_experience", "Yes")

    # ── Strengths / Skills ──
    if any(w in c for w in ["strength", "skill", "expertise", "competenc"]):
        return profile.get("skills", "Product Management, Data Analysis, Python, SQL, AI Tools")[:100]

    # ── Current company / organization ──
    if any(w in c for w in ["current company", "current org", "employer", "company name"]):
        return profile.get("current_company", "Apna Supermarket")

    # ── Current role / designation ──
    if any(w in c for w in ["current role", "current title", "designation"]):
        return profile.get("current_role", "Co-founder / Manager")

    # ── Yes/No type questions ──
    if any(w in c for w in ["authorized", "eligible", "legally", "willing", "relocat",
                             "agree", "confirm", "right to work"]):
        return "Yes"

    if any(w in c for w in ["sponsorship", "sponsor", "disability", "veteran",
                             "criminal", "conviction", "non-compete"]):
        return "No"

    # ── Location ──
    if any(w in c for w in ["current city", "city", "location", "based", "where are you"]):
        return profile.get("location", "Bangalore")

    # ── College / University ──
    if any(w in c for w in ["university", "college", "institution", "institute"]):
        return profile.get("college", "Manipal/T.A Pai Management Institute")

    # ── Course ──
    if any(w in c for w in ["what course", "course", "pursuing"]):
        return profile.get("course", "MBA")

    # ── Branch ──
    if any(w in c for w in ["branch", "department", "stream", "specialization"]):
        return profile.get("branch", "Technology Management")

    # ── Degree / Education ──
    if any(w in c for w in ["degree", "qualification"]):
        return profile.get("degree", "MBA")

    # ── Year of passing ──
    if any(w in c for w in ["passing year", "year of passing", "graduation year", "batch"]):
        return profile.get("graduation_year", "2027")

    # ── Generic fallback — use name instead of 'Yes' ──
    return profile.get("full_name", "Harsh Raghuwanshi")


def _smart_textarea_answer(combined, config):
    """
    Analyze what a textarea is asking and return a relevant answer.
    Don't dump the entire cover letter for every textarea.
    """
    profile = config.get("profile", {})
    cover_letter = config.get("cover_letter", "")
    c = combined.lower() if combined else ""

    # ── Cover letter / about yourself ──
    if any(w in c for w in ["cover letter", "about yourself", "tell us about",
                             "introduce yourself", "about you", "summary"]):
        return cover_letter or ("I am Harsh Raghuwanshi, pursuing MBA TECH at TAPMI Bengaluru. "
               "I have 4+ years of entrepreneurial experience as Co-founder of Apna Supermarket, "
               "with skills in product management, AI tools, and data analysis.")

    # ── Why do you want to join / motivation ──
    if any(w in c for w in ["why do you want", "why are you interested", "motivation",
                             "why this role", "why should we hire", "what excites",
                             "why are you applying"]):
        return ("I am drawn to this opportunity because it aligns with my experience in product management "
                "and growth strategy. At Apna Supermarket, I led product roadmapping, GTM strategy, and "
                "scaled revenue by 25%. I am eager to apply these skills in a dynamic environment and "
                "contribute meaningfully to the team's goals.")

    # ── Strengths / What do you bring ──
    if any(w in c for w in ["strength", "what do you bring", "what makes you",
                             "unique", "value add", "differentiate"]):
        return ("My key strengths include: 1) Hands-on product management experience from building a retail business, "
                "2) Technical skills in Python, SQL, Power BI for data-driven decisions, "
                "3) Experience with AI tools (Gemini, Claude) and automation, "
                "4) Strong cross-functional collaboration and leadership.")

    # ── Projects / Experience ──
    if any(w in c for w in ["project", "experience", "achievement", "accomplish",
                             "describe a time", "example", "past work"]):
        return ("As Co-founder of Apna Supermarket, I led product lifecycle management and growth initiatives. "
                "Key achievements include: 25% annual revenue growth, scaling turnover to ~₹2.5 Cr, "
                "implementing ERP/CRM systems, and building an AI-powered WhatsApp chatbot for customer orders. "
                "I also hold an IBM AI Product Manager certification.")

    # ── Skills / Technical ──
    if any(w in c for w in ["skill", "tool", "technical", "technology", "tech stack"]):
        return profile.get("skills", "Product Management, Python, SQL, Power BI, Figma, AI Tools")

    # ── Additional info / anything else ──
    if any(w in c for w in ["additional", "anything else", "other information", "comments",
                             "notes", "remarks", "supplementary"]):
        return ("I am available immediately for a 3-month internship and willing to relocate. "
                "I bring a unique combination of entrepreneurial experience and technical skills "
                "that would allow me to contribute from day one.")

    # ── Default: use cover letter for truly generic textareas ──
    if cover_letter:
        return cover_letter
    return ("I am Harsh Raghuwanshi, currently pursuing MBA TECH at TAPMI Bengaluru. "
            "I bring 4+ years of entrepreneurial experience with strong skills in "
            "product management, data analysis, and AI tools. I am eager to contribute "
            "meaningfully to this role.")



def fill_text_inputs(driver, config, container=None):
    """Fill empty text input fields using profile data matching."""
    filled = False
    field_rules = _build_field_rules(config)
    root = container or driver

    try:
        inputs = root.find_elements(By.CSS_SELECTOR,
            "input[type='text'], input[type='email'], input[type='tel'], "
            "input[type='url'], input:not([type])")
        for inp in inputs:
            try:
                if not inp.is_displayed():
                    continue
                val = (inp.get_attribute("value") or "").strip()
                if val:
                    continue

                combined = _get_field_label(driver, inp)
                if not combined:
                    continue

                matched = False
                for keywords, value in field_rules:
                    if value and any(kw in combined for kw in keywords):
                        inp.clear()
                        inp.send_keys(str(value))
                        filled = True
                        matched = True
                        display_label = combined[:40].strip()
                        print(f"    [Fill] {display_label}: {str(value)[:30]}")
                        break

                if not matched:
                    # Smart fallback — analyze the question before answering
                    inp_type = (inp.get_attribute("type") or "text").lower()
                    if inp_type == "email":
                        inp.send_keys(config.get("profile", {}).get("email", ""))
                    elif inp_type == "tel":
                        inp.send_keys(config.get("profile", {}).get("phone", ""))
                    elif inp_type == "url":
                        inp.send_keys(config.get("profile", {}).get("linkedin", ""))
                    else:
                        answer = _smart_text_answer(combined, config)
                        inp.send_keys(answer)
                    filled = True
                    print(f"    [Fill] ({combined[:40]}): {answer[:30] if 'answer' in dir() else 'type-based'}")

            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue
    except Exception:
        pass

    return filled


def fill_number_inputs(driver, config, container=None):
    """Fill numeric input fields."""
    filled = False
    profile = config.get("profile", {})
    root = container or driver

    try:
        inputs = root.find_elements(By.CSS_SELECTOR, "input[type='number']")
        for inp in inputs:
            try:
                if not inp.is_displayed():
                    continue
                val = (inp.get_attribute("value") or "").strip()
                if val and val != "0":
                    continue

                combined = _get_field_label(driver, inp)

                if any(w in combined for w in ["experience", "year", "exp"]):
                    inp.clear()
                    inp.send_keys(profile.get("years_experience", "4"))
                    print(f"    [Fill] Experience: {profile.get('years_experience', '4')}")
                elif any(w in combined for w in ["gpa", "cgpa", "grade", "percentage", "marks"]):
                    inp.clear()
                    inp.send_keys(profile.get("cgpa", "7.80"))
                    print(f"    [Fill] GPA: {profile.get('cgpa', '7.80')}")
                elif any(w in combined for w in ["salary", "ctc", "stipend", "compensation"]):
                    inp.clear()
                    inp.send_keys("0")
                    print("    [Fill] Salary: 0")
                elif any(w in combined for w in ["age"]):
                    inp.clear()
                    inp.send_keys(profile.get("age", "24"))
                    print(f"    [Fill] Age: {profile.get('age', '24')}")
                elif any(w in combined for w in ["phone", "mobile"]):
                    inp.clear()
                    inp.send_keys(profile.get("phone", ""))
                    print(f"    [Fill] Phone: {profile.get('phone', '')}")
                else:
                    inp.clear()
                    inp.send_keys("0")
                    print(f"    [Fill] Numeric ({combined[:30]}): 0")
                filled = True
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue
    except Exception:
        pass

    return filled


def fill_textareas(driver, config, container=None):
    """Fill textarea fields — analyze what's being asked first."""
    filled = False
    root = container or driver
    cover_letter = config.get("cover_letter", "")
    profile = config.get("profile", {})

    try:
        textareas = root.find_elements(By.CSS_SELECTOR, "textarea")
        for ta in textareas:
            try:
                if not ta.is_displayed():
                    continue
                val = (ta.get_attribute("value") or ta.text or "").strip()
                if val:
                    continue

                combined = _get_field_label(driver, ta)
                answer = _smart_textarea_answer(combined, config)
                ta.send_keys(answer)
                filled = True
                label_short = combined[:40] if combined else "text area"
                print(f"    [Fill] {label_short}: {answer[:50]}...")
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue
    except Exception:
        pass

    return filled


def fill_dropdowns(driver, config, container=None):
    """Handle <select> dropdowns — prefer 'Yes', then first valid option."""
    filled = False
    profile = config.get("profile", {})
    root = container or driver

    try:
        selects = root.find_elements(By.CSS_SELECTOR, "select")
        for sel_elem in selects:
            try:
                if not sel_elem.is_displayed():
                    continue
                sel = Select(sel_elem)
                current = (sel.first_selected_option.get_attribute("value") or "").strip()
                current_text = sel.first_selected_option.text.strip().lower()

                # Skip if already has a valid selection
                if current and current_text not in ["select", "select an option", "choose", "--", ""]:
                    continue

                combined = _get_field_label(driver, sel_elem)
                options = sel.options

                # Smart match: try to select the right value based on field label
                smart_selected = False

                if any(w in combined for w in ["gender", "sex"]):
                    for opt in options:
                        if profile.get("gender", "male").lower() in opt.text.strip().lower():
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown gender: {opt.text.strip()}")
                            break

                elif any(w in combined for w in ["country", "nationality"]):
                    for opt in options:
                        if "india" in opt.text.strip().lower():
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown country: {opt.text.strip()}")
                            break

                elif any(w in combined for w in ["degree", "qualification", "education"]):
                    for opt in options:
                        opt_text = opt.text.strip().lower()
                        if any(d in opt_text for d in ["mba", "post grad", "master", "pg"]):
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown degree: {opt.text.strip()}")
                            break

                elif any(w in combined for w in ["experience", "exp", "year"]):
                    for opt in options:
                        opt_text = opt.text.strip().lower()
                        if any(y in opt_text for y in ["3", "4", "3-5", "2-4", "1-3"]):
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown experience: {opt.text.strip()}")
                            break

                if not smart_selected:
                    # Analyze the question to decide Yes vs No
                    should_say_no = any(w in combined for w in [
                        "sponsorship", "sponsor", "disability", "handicap",
                        "veteran", "military", "criminal", "conviction",
                        "felony", "restrict", "non-compete",
                    ])
                    should_say_yes = any(w in combined for w in [
                        "authorized", "authorization", "eligible", "legally",
                        "relocat", "willing", "agree", "consent", "confirm",
                        "available", "immediate", "right to work", "permit",
                    ])

                    target_answer = None
                    if should_say_no:
                        target_answer = "no"
                    elif should_say_yes:
                        target_answer = "yes"

                    picked = False
                    if target_answer:
                        for opt in options:
                            if opt.text.strip().lower() == target_answer:
                                sel.select_by_visible_text(opt.text.strip())
                                picked = True
                                print(f"    [Fill] Dropdown ({combined[:30]}): {opt.text.strip()}")
                                break

                    if not picked:
                        # Select first non-empty option
                        for opt in options:
                            v = opt.get_attribute("value") or ""
                            t = opt.text.strip().lower()
                            if v and t not in ["select", "select an option", "choose", "--", ""]:
                                sel.select_by_value(v)
                                print(f"    [Fill] Dropdown ({combined[:30]}): {opt.text.strip()}")
                                break

                filled = True
            except (StaleElementReferenceException, ElementNotInteractableException):
                continue
            except Exception:
                continue
    except Exception:
        pass

    return filled


def fill_radio_buttons(driver, container=None):
    """Handle radio button groups — analyze the question context first."""
    filled = False
    root = container or driver

    try:
        fieldsets = root.find_elements(By.CSS_SELECTOR,
            "fieldset, .radio-group, .assessment_question, "
            "div[role='radiogroup'], .form-group")
        for fs in fieldsets:
            try:
                radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                if not radios or any(r.is_selected() for r in radios):
                    continue

                # Get the question context from the fieldset/group
                question_text = ""
                try:
                    question_text = fs.text.lower()
                    # Also check legend or heading
                    try:
                        legend = fs.find_element(By.CSS_SELECTOR, "legend, h3, h4, label, .question")
                        question_text = legend.text.lower() + " " + question_text
                    except:
                        pass
                except:
                    pass

                # Determine the right answer based on the question
                should_say_no = any(w in question_text for w in [
                    "sponsorship", "sponsor", "disability", "handicap",
                    "veteran", "military", "criminal", "conviction",
                    "non-compete", "restrict", "felony",
                ])
                should_say_yes = any(w in question_text for w in [
                    "authorized", "eligible", "legally", "relocat",
                    "willing", "agree", "consent", "confirm",
                    "available", "immediate", "right to work",
                    "terms", "condition", "acknowledge",
                ])

                target_answer = None
                if should_say_no:
                    target_answer = "no"
                elif should_say_yes:
                    target_answer = "yes"
                else:
                    target_answer = "yes"  # safe default for ambiguous yes/no

                # Collect all radio labels
                radio_labels = {}
                for radio in radios:
                    try:
                        label = None
                        radio_id = radio.get_attribute("id") or ""
                        if radio_id:
                            try:
                                label = driver.find_element(By.CSS_SELECTOR, f"label[for='{radio_id}']")
                            except:
                                pass
                        if not label:
                            try:
                                label = radio.find_element(By.XPATH,
                                    "./following-sibling::label | ./parent::label | "
                                    "./ancestor::div[1]//label")
                            except:
                                pass
                        if label:
                            radio_labels[radio] = label
                    except:
                        continue

                # Try to click the target answer
                clicked = False
                for radio, label in radio_labels.items():
                    label_text = label.text.strip().lower()
                    if label_text in [target_answer, "true", "agree", "i agree"] if target_answer == "yes" else [target_answer, "false", "disagree"]:
                        try_click(driver, label)
                        clicked = True
                        filled = True
                        q_short = question_text[:40].strip() if question_text else "radio"
                        print(f"    [Fill] Radio ({q_short}): {label.text.strip()}")
                        break

                if not clicked and radio_labels:
                    # Fall back to first option
                    first_radio = list(radio_labels.keys())[0]
                    first_label = radio_labels[first_radio]
                    try_click(driver, first_label)
                    filled = True
                    print(f"    [Fill] Radio: {first_label.text.strip()[:30]}")
            except:
                continue
    except Exception:
        pass

    return filled


def fill_checkboxes(driver, container=None):
    """Check any unchecked checkboxes (terms, agreements, etc.)."""
    filled = False
    root = container or driver

    try:
        checkboxes = root.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
        for cb in checkboxes:
            try:
                if not cb.is_displayed():
                    continue
                if not cb.is_selected():
                    try_click(driver, cb)
                    filled = True
                    print("    [Fill] Checkbox checked")
            except:
                continue
    except Exception:
        pass

    return filled


def upload_resume(driver, config, container=None):
    """Upload resume PDF if a file input is found."""
    uploaded = False
    resume_path = config.get("resume_path", "")
    if not resume_path:
        return False

    root = container or driver

    try:
        file_inputs = root.find_elements(By.CSS_SELECTOR, "input[type='file']")
        for fi in file_inputs:
            try:
                # Make visible if hidden
                driver.execute_script(
                    "arguments[0].style.display='block'; "
                    "arguments[0].style.opacity='1'; "
                    "arguments[0].style.position='relative';",
                    fi)
                fi.send_keys(resume_path)
                uploaded = True
                print(f"    [Resume] Uploaded: {resume_path.split('/')[-1]}")
                time.sleep(2)
            except Exception:
                continue
    except Exception:
        pass

    return uploaded


def fill_all_form_fields(driver, config, container=None):
    """
    Master function — fills ALL form fields on the current page/container.
    Call this on any job application form on any platform.
    Returns True if any field was filled.
    """
    filled = False
    from utils.auth import google_login_flow
    if google_login_flow(driver, "Form Automation", config.get("profile", {}).get("email", "")):
        filled = True
        print("    [SmartFill] 🔗 Google login automation triggered")

    filled |= upload_resume(driver, config, container)
    filled |= fill_text_inputs(driver, config, container)
    filled |= fill_number_inputs(driver, config, container)
    filled |= fill_textareas(driver, config, container)
    filled |= fill_dropdowns(driver, config, container)
    filled |= fill_radio_buttons(driver, container)
    filled |= fill_checkboxes(driver, container)

    if filled:
        print("    [SmartFill] ✅ Form fields filled")
    else:
        print("    [SmartFill] ℹ️  No empty fields found (form may be pre-filled)")

    return filled


def walk_multi_step_form(driver, config, max_steps=10):
    """
    Walk through a multi-step form (Next → Next → ... → Submit).
    Works for any platform that has multi-step application forms.
    Returns: 'submitted', 'stuck', or 'closed'
    """
    for step in range(max_steps):
        time.sleep(2)

        # Fill all fields on current step
        fill_all_form_fields(driver, config)
        time.sleep(1)

        # Check for success indicators
        try:
            success_texts = [
                "successfully", "applied", "submitted", "congratulations",
                "application has been", "thank you for applying",
                "application received", "you have applied"
            ]
            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(t in page_text for t in success_texts):
                print("    ✅ Application submitted successfully!")
                return "submitted"
        except:
            pass

        # Look for action buttons: Submit > Review > Next > Continue
        clicked = False
        button_priority = [
            "Submit application", "Submit", "Apply",
            "Review", "Next", "Continue", "Proceed",
            "Send application", "Confirm"
        ]

        for btn_text in button_priority:
            if clicked:
                break
            try:
                buttons = driver.find_elements(By.XPATH,
                    f"//button[contains(normalize-space(),'{btn_text}')] | "
                    f"//input[@type='submit' and contains(@value,'{btn_text}')] | "
                    f"//a[contains(normalize-space(),'{btn_text}')]")
                for btn in buttons:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            print(f"    [Step {step+1}] Clicking: '{btn.text.strip() or btn_text}'")
                            try_click(driver, btn)
                            clicked = True
                            time.sleep(2)

                            if "submit" in btn_text.lower() or "apply" in btn_text.lower():
                                # Verify submission
                                try:
                                    body = driver.find_element(By.TAG_NAME, "body").text.lower()
                                    if any(t in body for t in ["success", "applied", "submitted", "thank"]):
                                        print("    ✅ Submitted!")
                                        return "submitted"
                                except:
                                    pass
                                return "submitted"
                            break
                    except:
                        continue
            except:
                continue

        if not clicked:
            print(f"    [Step {step+1}] No actionable button found")
            # Check if we're still on a form page
            try:
                forms = driver.find_elements(By.CSS_SELECTOR, "form, .application-form")
                if not forms:
                    return "closed"
            except:
                pass

    return "stuck"
