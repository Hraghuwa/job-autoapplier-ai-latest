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


def _cover_note(config):
    """The cover/why text to fill: JD-tailored note when available, else the
    static one. Fail-open to the raw config value if the backend isn't on path."""
    try:
        from backend.services.cover_note import resolve_cover_note
        return resolve_cover_note(config)
    except Exception:
        return (config or {}).get("cover_letter", "")


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


def _kw_in_label(kw, combined):
    """Match a rule keyword against a field label WITHOUT substring false
    positives. The naive `kw in combined` filled the "Full Name" field with the
    last name because the keyword 'lname' is a substring of 'fullname'. Now:
    multi-word keywords match as a phrase; single-word keywords must match a
    whole word/token. Underscores/hyphens are normalised to spaces on both sides.
    """
    k = re.sub(r"[_\-]+", " ", str(kw).lower()).strip()
    if not k:
        return False
    c = re.sub(r"[_\-]+", " ", str(combined).lower())
    if " " in k:
        return k in c
    return k in set(re.split(r"[^a-z0-9]+", c))


def _stem_in_label(stem, combined):
    """Like _kw_in_label but matches a keyword as a word PREFIX — for intentional
    stems where the suffix varies ('authoriz'→authorized/authorization,
    'sponsor'→sponsorship, 'relocat'→relocate/relocation). Multi-word stems match
    as a phrase. Use this for yes/no question detection, NOT for field rules
    (a short stem like 'exp' must never prefix-match 'expected')."""
    s = re.sub(r"[_\-]+", " ", str(stem).lower()).strip()
    if not s:
        return False
    c = re.sub(r"[_\-]+", " ", str(combined).lower())
    if " " in s:
        return s in c
    return any(w.startswith(s) for w in re.split(r"[^a-z0-9]+", c) if w)


def _get_field_label(driver, element):
    """Extract the label/context for a form field.

    A field can carry an AUTHORITATIVE label (an explicit <label for>, aria-label,
    placeholder, or wrapping <label>). When one exists we use ONLY those + the
    field-local name/id — never the document-order fallbacks, which previously
    leaked the *previous* field's label (e.g. `./preceding::label[1]`) and filled
    email/phone with the candidate's name. The greedy fallbacks run only for
    truly label-less forms, and even then stay scoped to the field's own
    container.
    """
    strong = []   # authoritative, field-owned labels
    weak = []     # name/id — safe local disambiguators

    # 1. Explicit <label for="id">
    inp_id = element.get_attribute("id") or ""
    if inp_id:
        try:
            label_el = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
            if label_el.text.strip():
                strong.append(label_el.text)
        except NoSuchElementException:
            pass

    # 2. aria-label / aria-labelledby target
    aria = element.get_attribute("aria-label") or ""
    if aria:
        strong.append(aria)

    # 3. placeholder
    placeholder = element.get_attribute("placeholder") or ""
    if placeholder:
        strong.append(placeholder)

    # 4. Wrapping <label> ancestor (the field is INSIDE its own label)
    try:
        parent_label = element.find_element(By.XPATH, "./ancestor::label")
        if parent_label.text.strip():
            strong.append(parent_label.text)
    except Exception:
        pass

    # name / id are always safe (field-owned attributes).
    name = element.get_attribute("name") or ""
    if name:
        weak.append(name.replace("_", " ").replace("-", " "))
    if inp_id:
        weak.append(inp_id.replace("_", " ").replace("-", " "))

    if strong:
        return " ".join(strong + weak).lower().strip()

    # ── Fallbacks ONLY for label-less forms — stay within the field's container
    # so we cannot pick up a sibling field's label. NO global preceding::label.
    fallback = []
    try:
        sib = element.find_element(By.XPATH, "./preceding-sibling::label[1]")
        if sib.text.strip():
            fallback.append(sib.text)
    except Exception:
        pass
    if not fallback:
        try:
            container_label = element.find_element(
                By.XPATH, "(./ancestor::div[1]//label | ./ancestor::fieldset[1]//legend)[1]")
            if container_label.text.strip():
                fallback.append(container_label.text)
        except Exception:
            pass
    if not fallback:
        try:
            parent_div = element.find_element(By.XPATH, "./ancestor::div[1]")
            div_text = parent_div.text.split("\n")[0]
            if div_text and len(div_text) < 100:
                fallback.append(div_text)
        except Exception:
            pass

    return " ".join(fallback + weak).lower().strip()


def _build_field_rules(config):
    """
    Build matching rules from the user's profile data.

    Values come STRICTLY from CONFIG["profile"]. When a field is not
    provided by the user, the rule is DROPPED from the returned list
    rather than being filled with placeholder data belonging to
    another candidate. This keeps the module multi-tenant safe.
    """
    profile = config.get("profile", {}) or {}

    # Derive first/last name from full_name if explicit fields missing.
    _full = profile.get("full_name") or config.get("name")
    _first = profile.get("first_name") or ((_full.split(" ", 1)[0]) if _full else None)
    _last = profile.get("last_name") or ((" ".join(_full.split(" ")[1:]) or None) if _full else None)

    _email = config.get("email") or profile.get("email")
    _phone = profile.get("phone") or profile.get("phone_number") or profile.get("mobile")
    _linkedin = profile.get("linkedin") or profile.get("linkedin_url")
    _portfolio = (profile.get("personal_website") or profile.get("portfolio")
                  or profile.get("portfolio_url") or profile.get("website"))
    _city = profile.get("city") or profile.get("location")
    _cgpa = profile.get("cgpa") or profile.get("gpa") or profile.get("percentage")
    _grad_year = profile.get("graduation_year") or profile.get("year_of_passing")
    _years_exp = (profile.get("years_experience")
                  or profile.get("total_experience")
                  or profile.get("experience_years"))
    _cur_company = profile.get("current_company") or profile.get("company")
    _cur_role = profile.get("current_role") or profile.get("current_title") or profile.get("designation")
    _exp_salary = profile.get("expected_salary") or profile.get("expected_ctc")
    _cur_ctc = profile.get("current_ctc") or profile.get("current_salary")
    _notice_period = profile.get("notice_period")
    _join_date = profile.get("join_date") or profile.get("availability")
    _skills = profile.get("skills") or profile.get("skill_list")
    _college = profile.get("college") or profile.get("university")
    _course = profile.get("course") or profile.get("degree")
    _branch = profile.get("branch") or profile.get("specialization")
    _degree = profile.get("degree") or profile.get("course")

    raw_rules = [
        # Name fields
        (["first name", "given name", "fname", "first_name"], _first),
        (["last name", "surname", "family name", "lname", "last_name"], _last),
        (["full name", "your name", "candidate name", "applicant name", "fullname"], _full),
        (["name"], _full),

        # Contact
        (["phone", "mobile", "contact number", "contact no", "tel", "whatsapp"], _phone),
        (["email", "e-mail", "mail id", "mail", "email id"], _email),
        (["linkedin", "linkedin id", "linkedin url", "profile url"], _linkedin),
        (["portfolio", "website", "personal website", "link to your work"], _portfolio),
        (["github"], profile.get("github") or profile.get("github_url")),

        # Location
        (["city", "current city", "hometown", "town", "current location"], _city),
        (["location", "address", "place", "based", "currently based"], _city),
        (["street", "address line"], profile.get("address")),
        (["country", "nationality"], profile.get("country")),
        (["state", "province"], profile.get("state")),
        (["pin", "zip", "postal"], profile.get("pincode") or profile.get("postal_code")),

        # Education
        (["university", "college", "school", "institution", "institute", "name of your college", "college name"], _college),
        (["course", "what course", "pursuing", "completed"], _course),
        (["degree", "qualification", "program"], _degree),
        (["branch", "department", "stream", "specialization", "mention your branch"], _branch),
        (["major", "field of study"], _branch),
        (["gpa", "cgpa", "percentage", "grade", "score", "marks"], _cgpa),
        (["graduation", "passing year", "year of passing", "end year", "year of completion", "completion year", "batch"], _grad_year),

        # Experience & Work
        (["years of experience", "total experience", "work experience", "exp", "years of professional", "years of relevant"], _years_exp),
        (["duration", "internship period", "how long", "tenure"], profile.get("internship_duration")),
        (["notice period", "notice"], (f"{_notice_period} days" if _notice_period else None)),
        (["how soon", "when can you join", "join date", "start date", "joining date", "date of joining", "available from", "availability", "earliest date"], _join_date),
        (["current company", "current organization", "employer", "company name", "organisation"], _cur_company),
        (["current role", "current title", "last role", "current/last role", "designation", "job title"], _cur_role),

        # Salary / Stipend
        (["expected salary", "expected compensation", "expected ctc", "salary expectation", "expected stipend"], _exp_salary),
        (["current salary", "current ctc", "current compensation", "previous salary", "last drawn", "present salary", "present ctc", "current stipend"], _cur_ctc),
        (["salary", "ctc", "compensation", "stipend"], _exp_salary),

        # Laptop
        (["laptop", "do you have a laptop"], profile.get("has_laptop")),

        # AI / Product experience — only filled if the user provided something
        (["tools have you used", "which tools", "tools used"], profile.get("tools_used")),
        (["rag", "retrieval augmented", "retrieval-augmented"], profile.get("rag_explanation")),
        (["product", "startup", "ai-related project", "ai related", "worked on any product"], profile.get("has_product_ai_experience")),

        # Authorization / eligibility
        (["authorized", "authorization", "legally", "eligible", "visa", "permit", "right to work"], profile.get("legally_authorized")),
        (["sponsorship", "sponsor", "work permit"], profile.get("require_sponsorship")),
        (["relocat", "willing to relocate", "relocation"], profile.get("willing_to_relocate")),
        (["how did you hear", "source", "referral", "where did you find"], profile.get("heard_about_us")),

        # Skills
        (["skill", "expertise", "competenc", "technologies", "tech stack"], _skills),
        (["tools", "software", "platforms"], profile.get("tools") or _skills),
        (["certif", "certificate"], profile.get("certifications")),

        # Gender / DOB
        (["gender", "sex"], profile.get("gender")),
        (["age", "date of birth", "dob", "birth"], profile.get("age") or profile.get("date_of_birth")),
    ]
    # Drop rules whose value is empty so the caller doesn't write placeholder data.
    return [(keys, val) for (keys, val) in raw_rules if val not in (None, "", [])]


def _smart_text_answer(combined, config):
    """
    Analyze what a text field is asking and return a logical answer from the
    user's profile. Returns None if the user has no data for the field —
    the caller then decides whether to skip or use a generic placeholder.
    """
    profile = config.get("profile", {}) or {}
    c = (combined or "").lower()

    def _p(*keys):
        for k in keys:
            v = profile.get(k)
            if v:
                return v
        return None

    # ── LinkedIn ──
    if any(w in c for w in ["linkedin", "linkedin id", "linkedin url"]):
        return _p("linkedin", "linkedin_url")

    # ── Email ── (config.email is the logged-in user's email)
    if any(w in c for w in ["email", "e-mail", "mail id", "email id"]):
        return config.get("email") or _p("email")

    # ── Phone ──
    if any(w in c for w in ["phone", "mobile", "contact no", "contact number", "whatsapp"]):
        return _p("phone", "phone_number", "mobile")

    # ── CGPA ──
    if any(w in c for w in ["cgpa", "gpa", "percentage", "marks", "score"]):
        return _p("cgpa", "gpa", "percentage")

    # ── Motivation / Why questions — use saved cover letter or skip ──
    if any(w in c for w in ["why do you want", "why are you", "motivation", "interest in",
                             "why this", "why should we", "what excites"]):
        return (_cover_note(config) or _p("cover_letter", "motivation", "why_this_role"))

    # ── Where did you hear about us ──
    if any(w in c for w in ["how did you hear", "where did you find", "source", "referral",
                             "how did you learn", "how did you know"]):
        return _p("heard_about_us")

    # ── Join date / Availability / Start date ──
    if any(w in c for w in ["how soon", "when can you join", "start date", "join date",
                             "joining date", "date of joining", "available from",
                             "earliest", "availability", "earliest date"]):
        return _p("join_date", "availability", "earliest_start_date")

    # ── Notice period ──
    if any(w in c for w in ["notice period", "notice"]):
        np = _p("notice_period")
        return f"{np} days" if np else None

    # ── Duration / How long ──
    if any(w in c for w in ["duration", "how long", "tenure"]):
        return _p("internship_duration")

    # ── Current / Previous Salary / Stipend ──
    if any(w in c for w in ["current salary", "current ctc", "current compensation",
                             "previous salary", "last drawn", "present salary",
                             "present ctc", "current stipend"]):
        return _p("current_ctc", "current_salary")

    # ── Expected Salary / Stipend ──
    if any(w in c for w in ["expected salary", "expected ctc", "salary expectation",
                             "expected compensation", "expected stipend"]):
        return _p("expected_salary", "expected_ctc")

    # ── Generic salary fallback ──
    if any(w in c for w in ["salary", "ctc", "compensation", "stipend"]):
        return _p("expected_salary", "expected_ctc")

    # ── Experience ──
    if any(w in c for w in ["years of experience", "total experience", "work experience",
                             "years of professional", "years of relevant"]):
        return _p("years_experience", "total_experience", "experience_years")

    # ── Current/Last role ──
    if any(w in c for w in ["current role", "current title", "last role",
                             "current/last role", "designation"]):
        return _p("current_role", "current_title", "designation")

    # ── Laptop ──
    if any(w in c for w in ["laptop", "do you have a laptop"]):
        return _p("has_laptop") or "Yes"

    # ── RAG explanation ──
    if any(w in c for w in ["rag", "retrieval augmented", "retrieval-augmented"]):
        return _p("rag_explanation")

    # ── Tools used ──
    if any(w in c for w in ["tools have you used", "which tools", "tools used"]):
        return _p("tools_used", "tech_stack", "skills")

    # ── Product/AI experience ──
    if any(w in c for w in ["product", "startup", "ai-related project", "worked on any"]):
        return _p("has_product_ai_experience") or "Yes"

    # ── Strengths / Skills ──
    if any(w in c for w in ["strength", "skill", "expertise", "competenc"]):
        skills = _p("skills", "skill_list")
        return (skills[:100] if skills else None)

    # ── Current company / organization ──
    if any(w in c for w in ["current company", "current org", "employer", "company name"]):
        return _p("current_company", "company")

    # ── Yes/No type questions ──
    if any(w in c for w in ["authorized", "eligible", "legally", "willing", "relocat",
                             "agree", "confirm", "right to work"]):
        return "Yes"

    if any(w in c for w in ["sponsorship", "sponsor", "disability", "veteran",
                             "criminal", "conviction", "non-compete"]):
        return "No"

    # ── Location ──
    if any(w in c for w in ["current city", "city", "location", "based", "where are you"]):
        return _p("location", "city", "current_city")

    # ── College / University ──
    if any(w in c for w in ["university", "college", "institution", "institute"]):
        return _p("college", "university")

    # ── Course ──
    if any(w in c for w in ["what course", "course", "pursuing"]):
        return _p("course", "degree")

    # ── Branch ──
    if any(w in c for w in ["branch", "department", "stream", "specialization"]):
        return _p("branch", "specialization")

    # ── Degree / Education ──
    if any(w in c for w in ["degree", "qualification"]):
        return _p("degree", "course")

    # ── Year of passing ──
    if any(w in c for w in ["passing year", "year of passing", "graduation year", "batch"]):
        return _p("graduation_year", "year_of_passing")

    # ── Generic fallback — use the user's full name if available, else None ──
    return _p("full_name", "name") or config.get("name")


def _smart_textarea_answer(combined, config):
    """
    Analyze what a textarea is asking and return a relevant answer from the
    user's saved data (cover letter, profile bio, etc.). If the user has
    nothing suitable on file, we synthesize a generic one-liner from their
    profile name + current role rather than making up a fake bio.
    """
    profile = config.get("profile", {}) or {}
    cover_letter = (_cover_note(config) or "").strip()
    bio = (profile.get("bio") or profile.get("about_me") or "").strip()
    c = (combined or "").lower()

    cand_name = profile.get("full_name") or config.get("name") or "the candidate"
    cand_role = (profile.get("current_role")
                 or profile.get("current_title")
                 or profile.get("target_role")
                 or "my field")

    def _generic_intro():
        """A neutral, content-free intro derived from whatever the user provided."""
        return (
            f"Hi, I'm {cand_name}. I'm excited about this role and believe my "
            f"background in {cand_role} aligns with what you're looking for. "
            "I'd love to discuss how I can contribute to the team."
        )

    # ── Cover letter / about yourself ──
    if any(w in c for w in ["cover letter", "about yourself", "tell us about",
                             "introduce yourself", "about you", "summary"]):
        return cover_letter or bio or _generic_intro()

    # ── Why do you want to join / motivation ──
    if any(w in c for w in ["why do you want", "why are you interested", "motivation",
                             "why this role", "why should we hire", "what excites",
                             "why are you applying"]):
        return (profile.get("why_this_role")
                or profile.get("motivation")
                or cover_letter
                or _generic_intro())

    # ── Strengths / What do you bring ──
    if any(w in c for w in ["strength", "what do you bring", "what makes you",
                             "unique", "value add", "differentiate"]):
        return profile.get("strengths") or profile.get("skills") or None

    # ── Projects / Experience ──
    if any(w in c for w in ["project", "experience", "achievement", "accomplish",
                             "describe a time", "example", "past work"]):
        return (profile.get("achievements")
                or profile.get("notable_projects")
                or profile.get("experience_summary")
                or None)

    # ── Skills / Technical ──
    if any(w in c for w in ["skill", "tool", "technical", "technology", "tech stack"]):
        return profile.get("skills") or profile.get("tech_stack") or profile.get("tools_used")

    # ── Additional info / anything else ──
    if any(w in c for w in ["additional", "anything else", "other information", "comments",
                             "notes", "remarks", "supplementary"]):
        return profile.get("additional_info") or None

    # ── Default: prefer the user's saved cover letter, then bio, then skip ──
    return cover_letter or bio or None



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
                    if value and any(_kw_in_label(kw, combined) for kw in keywords):
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
    cover_letter = _cover_note(config)
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

                if _kw_in_label("gender", combined) or _kw_in_label("sex", combined):
                    for opt in options:
                        if profile.get("gender", "male").lower() in opt.text.strip().lower():
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown gender: {opt.text.strip()}")
                            break

                elif _kw_in_label("country", combined) or _kw_in_label("nationality", combined):
                    for opt in options:
                        if "india" in opt.text.strip().lower():
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown country: {opt.text.strip()}")
                            break

                elif any(_kw_in_label(w, combined) for w in ["degree", "qualification", "education"]):
                    for opt in options:
                        opt_text = opt.text.strip().lower()
                        if any(d in opt_text for d in ["mba", "post grad", "master", "pg"]):
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown degree: {opt.text.strip()}")
                            break

                # Whole-word "experience"/"years" only — never the substring 'exp'
                # (which used to match 'expected salary' and fill it with a years range).
                elif any(_kw_in_label(w, combined) for w in ["experience", "years"]):
                    for opt in options:
                        opt_text = opt.text.strip().lower()
                        if any(y in opt_text for y in ["3", "4", "3-5", "2-4", "1-3"]):
                            sel.select_by_visible_text(opt.text.strip())
                            smart_selected = True
                            print(f"    [Fill] Dropdown experience: {opt.text.strip()}")
                            break

                if not smart_selected:
                    # Analyze the question to decide Yes vs No (stem-matched).
                    should_say_no = any(_stem_in_label(w, combined) for w in [
                        "sponsor", "disability", "handicap",
                        "veteran", "military", "criminal", "convict",
                        "felony", "restrict", "non-compete",
                    ])
                    should_say_yes = any(_stem_in_label(w, combined) for w in [
                        "authoriz", "eligible", "legally",
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

                # Try to click the target answer.
                # NOTE: the previous one-liner `x in A if C else B` parsed as
                # `(x in A) if C else B` — so for a "no" answer the condition
                # became the truthy list B and clicked the FIRST radio (Yes),
                # i.e. "Yes" to sponsorship/disability/felony. Fixed below.
                if target_answer == "yes":
                    accept = {"yes", "true", "agree", "i agree", "y"}
                else:
                    accept = {"no", "false", "disagree", "n"}
                clicked = False
                for radio, label in radio_labels.items():
                    label_text = label.text.strip().lower()
                    if label_text in accept:
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


# Checkboxes we must NOT auto-tick: marketing opt-ins and negative/decline boxes.
# Blindly checking every box used to opt the user into promo email and tick
# "I do NOT consent" boxes — actively harmful.
_CHECKBOX_SKIP = (
    "do not", "don't", "do n't", "opt out", "opt-out", "unsubscribe",
    "newsletter", "promotional", "promotions", "marketing", "subscribe",
    "third party", "third-party", "do you not", "decline",
)
# Boxes that are safe/required to tick so the form will submit.
_CHECKBOX_ALLOW = (
    "agree", "terms", "consent", "privacy", "policy", "acknowledge",
    "confirm", "accept", "i have read", "authorize", "certify", "declare",
)


def fill_checkboxes(driver, container=None):
    """Tick consent/terms checkboxes (needed to submit) but skip marketing
    opt-ins and negative 'I do not...' boxes. Label-aware to avoid opting the
    user into things they didn't ask for."""
    filled = False
    root = container or driver

    try:
        checkboxes = root.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
        for cb in checkboxes:
            try:
                if not cb.is_displayed() or cb.is_selected():
                    continue
                label = _get_field_label(driver, cb)
                if label and any(s in label for s in _CHECKBOX_SKIP):
                    print(f"    [Skip] Checkbox (opt-in/negative): {label[:40]}")
                    continue
                # Tick when it's a clear consent/terms box, or when unlabeled
                # (many required boxes have no readable label) — but never the
                # skip-listed ones handled above.
                if (not label) or any(a in label for a in _CHECKBOX_ALLOW):
                    try_click(driver, cb)
                    filled = True
                    print(f"    [Fill] Checkbox: {label[:40] or 'unlabeled'}")
            except Exception:
                continue
    except Exception:
        pass

    return filled


def _capture_jd_text(driver, config):
    """Return the JD text for the page being applied to, or None.

    Priority: an explicitly-set config['_current_jd'] (an applier that scraped
    the real JD) wins; otherwise the current page's visible body text serves as
    JD context — at upload time the applier is ON the job/application page, so
    its text is the best available signature (jd_analyser truncates to 8k and
    filters hallucinated must-haves against this same text, so page chrome is
    tolerated). Pages too short to carry a JD signal (< 80 chars) and any
    driver failure return None, which keeps the static-PDF fallback.
    """
    explicit = (config or {}).get("_current_jd")
    if explicit:
        return explicit
    try:
        body = driver.find_element(By.TAG_NAME, "body").text or ""
        body = body.strip()
        if len(body) < 80:
            return None
        return body[:8000]
    except Exception:
        return None


def _passes_fit_gate(driver, config):
    """Return True if the agent should proceed to apply, False to skip.

    Consults backend.services.apply_decision.should_apply with the page's JD
    text + the job title. Fail-OPEN: missing backend, no JD text, or any error
    → True (apply), so the gate can only prevent waste, never block a working
    flow. Prints a '⏭ Skipping (fit ...)' line on veto so the worker's stdout
    classifier records a skipped event with the reason.
    """
    try:
        from backend.services.apply_decision import should_apply
    except Exception:
        return True  # standalone/CLI without backend on path → no gate
    try:
        jd = _capture_jd_text(driver, config)
        title = (config or {}).get("_current_title") or ""
        if not title:
            try:
                title = (driver.title or "").strip()
            except Exception:
                title = ""
        decision = should_apply(config or {}, jd_text=jd, title=title or None)
        if not decision.apply:
            print(f"    ⏭ Skipping (fit {decision.score}/100): {decision.reasons[-1]}")
            return False
        # We're going to apply — tailor the cover note ONCE for this job and
        # stash it so every "why this role" field reuses it (fail-open inside).
        _prepare_cover_note(config, jd)
        return True
    except Exception:
        return True


def _prepare_cover_note(config, jd_text):
    """Generate a JD-tailored cover note once per application → config[
    '_tailored_cover_note']. Best-effort; leaves the static note in place on
    any failure."""
    try:
        from backend.services.cover_note import generate
        note = generate((config or {}).get("profile") or {}, jd_text=jd_text,
                        config=config or {})
        if note:
            config["_tailored_cover_note"] = note
    except Exception:
        pass


def upload_resume(driver, config, container=None):
    """Upload resume PDF if a file input is found.

    Audit M7: prefer the JD-tailored PDF when we have JD context. Internshala,
    web-search, and form-fill all route their uploads through here, so wiring
    the resolver at this chokepoint extends Phase E beyond LinkedIn/Wellfound.
    resolve_resume_path falls back to the static PDF whenever JD text or the
    tailoring context is missing, so this can never regress to "no upload".
    """
    uploaded = False
    resume_path = config.get("resume_path", "")
    try:
        from backend.services.resume_resolver import resolve_resume_path
        jd_text = _capture_jd_text(driver, config)
        resume_path = resolve_resume_path(config, jd_text=jd_text) or resume_path
    except Exception:
        pass
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
    Returns: 'submitted', 'stuck', 'closed', or 'skipped' (fit gate vetoed).
    """
    # ── Fit gate (PLAN match gate): internshala / workday / generic web-search
    # all funnel through here, so one check stops the agent wasting an apply on
    # a job the candidate can't win or shouldn't take. Fail-open on any error.
    if not _passes_fit_gate(driver, config):
        return "skipped"

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
                print("    ✅ SUCCESS: Application submitted successfully!")
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
                            btn_label = btn.text.strip() or btn.get_attribute("value") or btn_text
                            print(f"    🚀 [Step {step+1}] ACTION: Clicking '{btn_label}'")
                            try_click(driver, btn)
                            clicked = True
                            time.sleep(3) # Give it more time

                            if "submit" in btn_text.lower() or "apply" in btn_text.lower():
                                # Verify submission
                                print("    ⏳ Verifying submission...")
                                time.sleep(2)
                                try:
                                    body = driver.find_element(By.TAG_NAME, "body").text.lower()
                                    if any(t in body for t in ["success", "applied", "submitted", "thank", "congratulations"]):
                                        print("    ✅ SUCCESS: Confirmed submission!")
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
