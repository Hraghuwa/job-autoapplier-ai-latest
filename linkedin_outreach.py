"""
🤝 LinkedIn Outreach Agent — Phase 4 (GenAI Powered)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Searches LinkedIn for intern jobs, finds the recruiter/HR who posted,
analyzes the JD with Gemini AI, and sends a uniquely personalized
connection request crafted by AI for each specific job.

Connection note: max 300 chars — AI-crafted per job/company/JD.
Direct message: longer AI-crafted message for existing connections.
"""

import time
import random
import traceback
import os
from urllib.parse import quote_plus

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    StaleElementReferenceException, ElementNotInteractableException
)

# ─────────────────────────────────────────────
#  GEMINI AI SETUP
# ─────────────────────────────────────────────
_genai_client = None

def _get_genai_client(config):
    """Lazy-init Gemini client."""
    global _genai_client
    if _genai_client is not None:
        return _genai_client

    api_key = config.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("  ⚠️  No Gemini API key — using template messages")
        return None

    try:
        from google import genai
        _genai_client = genai.Client(api_key=api_key)
        print("  🧠 Gemini AI connected for personalized messages!")
        return _genai_client
    except Exception as e:
        print(f"  ⚠️  Gemini init error: {e}")
        return None


from utils.performance import COST_OPTIMIZER

def _call_gemini(prompt, config, max_retries=2):
    """Call Gemini with retry on rate limit and track costs."""
    client = _get_genai_client(config)
    if not client:
        return None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = response.text.strip().strip('"').strip("'")
            
            # Log approximate token usage for cost optimization
            COST_OPTIMIZER.log_usage(input_chars=prompt, output_chars=text)
            
            return text if len(text) >= 20 else None
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "exhausted" in err or "429" in err:
                if attempt < max_retries:
                    wait = 30 * (attempt + 1)
                    print(f"      ⏳ Rate limit, waiting {wait}s...")
                    time.sleep(wait)
                    continue
            print(f"      ⚠️  AI error: {str(e)[:60]}")
            return None
    return None


def ai_craft_connection_note(job_title, company_name, jd_text, recruiter_name, config):
    """
    Use Gemini AI to craft a unique, personalized connection note.
    Max 300 characters. Falls back to template if AI fails.
    """
    prompt = f"""You are writing a LinkedIn connection request note for Harsh Raghuwanshi.
The note MUST be under 280 characters (strict limit). Be conversational, warm, and specific.

Harsh's background:
- MBA student at T.A Pai Management Institute (TAPMI), Bengaluru
- 4+ years entrepreneurial experience as Cofounder of Apna Supermarket (~₹2.5 Cr turnover)
- Skills: Product Management, GTM Strategy, Python, SQL, Power BI, AI Tools
- IBM AI Product Manager certified
- Built AI WhatsApp chatbot using Gemini & Claude

Job details:
- Title: {job_title}
- Company: {company_name}
- Recruiter/Poster: {recruiter_name}
- JD highlights: {jd_text[:500]}

Write a SHORT, personalized connection note (under 280 chars) that:
1. Addresses the recruiter by first name if available
2. Mentions something SPECIFIC from the JD or company
3. Connects Harsh's relevant experience to this specific role
4. Sounds natural, not robotic or generic
5. Ends with a soft call-to-action

IMPORTANT: Output ONLY the note text. No quotes, no explanations. Under 280 characters."""

    note = _call_gemini(prompt, config)
    if note and len(note) > 300:
        note = note[:297] + "..."
    return note


def ai_craft_direct_message(job_title, company_name, jd_text, recruiter_name, config):
    """
    Use Gemini AI to craft a personalized direct message.
    Used when already connected with the person.
    """
    prompt = f"""You are writing a LinkedIn direct message for Harsh Raghuwanshi to a recruiter/hiring manager.
Keep it professional but warm. Max 800 characters.

Harsh's background:
- Harsh Raghuwanshi, MBA at T.A Pai Management Institute (TAPMI), Bengaluru (2025-2027)
- Cofounder of Apna Supermarket — ₹2.5 Cr turnover, 25% YoY growth
- 4+ years entrepreneurial experience in product management, GTM, operations
- Skills: Product Roadmapping, Agile, Python, SQL, Power BI, Figma, AI Tools
- IBM AI Product Manager certified, built AI chatbot with Gemini & Claude
- Available to join from April 2026, based in Bengaluru
- LinkedIn: https://www.linkedin.com/in/harsh-raghuwanshi-570868359/

Job details:
- Title: {job_title}
- Company: {company_name}
- Recruiter/Poster: {recruiter_name}
- JD: {jd_text[:800]}

Write a personalized message that:
1. Greets the recruiter by first name if available
2. References the SPECIFIC role and something from the JD
3. Highlights 2-3 of Harsh's most relevant experiences for THIS role
4. Mentions availability (April 2026) and location (Bengaluru)
5. Asks politely for consideration or referral
6. Signs off as Harsh Raghuwanshi, MBA TECH | TAPMI

IMPORTANT: Output ONLY the message text. No quotes. Under 800 characters."""

    return _call_gemini(prompt, config)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def safe_wait(driver, selector, timeout=5):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
    except TimeoutException:
        return None


def safe_click(driver, element):
    try:
        element.click()
        return True
    except:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except:
            return False


def scroll_into_view(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.5)
    except:
        pass


# ─────────────────────────────────────────────
#  JD ANALYZER — Extract key info from job post
# ─────────────────────────────────────────────
def analyze_jd(jd_text, job_title, company_name):
    """
    Analyze a job description and extract key themes for personalization.
    Returns a dict with relevant talking points.
    """
    jd_lower = jd_text.lower() if jd_text else ""

    themes = {
        "is_product": any(w in jd_lower for w in [
            "product management", "product manager", "roadmap", "prd",
            "user stories", "agile", "sprint", "backlog",
        ]),
        "is_ai": any(w in jd_lower for w in [
            "ai", "machine learning", "ml", "data science", "nlp",
            "generative ai", "llm", "deep learning", "chatbot",
        ]),
        "is_business": any(w in jd_lower for w in [
            "business", "strategy", "consulting", "analyst",
            "market research", "competitive analysis", "gtm",
        ]),
        "is_founder_office": any(w in jd_lower for w in [
            "founder", "ceo", "chief of staff", "growth",
            "cross-functional", "startup",
        ]),
        "is_operations": any(w in jd_lower for w in [
            "operations", "supply chain", "logistics", "process",
            "efficiency", "automation",
        ]),
        "needs_data": any(w in jd_lower for w in [
            "data", "sql", "python", "analytics", "power bi",
            "tableau", "excel", "dashboard",
        ]),
        "needs_design": any(w in jd_lower for w in [
            "figma", "design thinking", "wireframe", "prototype",
            "user experience", "ux", "ui",
        ]),
        "is_startup": any(w in jd_lower for w in [
            "startup", "fast-paced", "0 to 1", "zero to one",
            "early stage", "series a", "series b",
        ]),
    }

    return themes


def craft_connection_note(job_title, company_name, jd_text, recruiter_name, themes, config):
    """
    Craft a personalized connection note (max 300 chars).
    Uses the user-provided exact template.
    """
    note = "Hello, I’m Harsh Raghuwanshi from T.A. Pai Management Institute (TAPMI). I’m reaching out to explore Summer 2026 internships. My interest is at the intersection of tech & business (Tech Consulting, PM, BD). I’d value the chance to discuss how my MBA background can contribute to your team."
    
    if len(note) > 300:
        note = note[:297] + "..."
    return note


def craft_direct_message(job_title, company_name, jd_text, recruiter_name, themes, config):
    """
    Craft a personalized DM. Tries AI first, falls back to template.
    """
    # Try GenAI first
    ai_msg = ai_craft_direct_message(job_title, company_name, jd_text, recruiter_name, config)
    if ai_msg:
        print(f"        🧠 AI-crafted message ({len(ai_msg)} chars)")
        return ai_msg

    # Fallback template
    profile = config.get("profile", {})
    name = profile.get("full_name", "Harsh Raghuwanshi")
    linkedin = profile.get("linkedin", "")

    msg = (
        f"Hi,\n\n"
        f"I'm {name}, pursuing MBA at TAPMI Bengaluru.\n\n"
        f"I came across the {job_title} role at {company_name} and I'm very interested. "
        f"I bring 4+ years of entrepreneurial exp as Cofounder of Apna Supermarket. "
        f"I'm skilled in Product Management, Python, SQL, AI Tools.\n\n"
        f"Available to join from April 2026. Would appreciate any guidance or referral.\n\n"
        f"Best,\n{name}\nMBA TECH | TAPMI\n{linkedin}"
    )
    return msg


# ─────────────────────────────────────────────
#  FIND RECRUITER / HR FROM JOB POST
# ─────────────────────────────────────────────
def find_job_poster(driver, job_card_or_page):
    """
    Try to find the person who posted a LinkedIn job.
    Returns dict with name, title, profile_url, or None.
    """
    poster_info = None

    try:
        # Method 1: Look for "Posted by" section on job detail page
        poster_selectors = [
            ".job-details-jobs-unified-top-card__hiring-manager",
            ".jobs-poster__name",
            "a[data-tracking-control-name*='hiring_team']",
            ".hirer-card__hirer-information a",
            "a[href*='/in/'][data-tracking-control-name*='jobposting']",
            ".jobs-unified-top-card__subtitle-primary-grouping a",
        ]

        for sel in poster_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    href = el.get_attribute("href") or ""
                    name = el.text.strip()
                    if href and "/in/" in href and name:
                        poster_info = {
                            "name": name,
                            "profile_url": href.split("?")[0],
                            "element": el,
                        }
                        return poster_info
            except:
                continue

        # Method 2: Look for recruiter mentions in job description
        try:
            jd_section = driver.find_element(By.CSS_SELECTOR,
                ".jobs-description, .jobs-box__html-content, "
                ".job-details-jobs-unified-top-card__job-insight")
            jd_links = jd_section.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")
            for link in jd_links:
                href = link.get_attribute("href") or ""
                name = link.text.strip()
                if href and name:
                    poster_info = {
                        "name": name,
                        "profile_url": href.split("?")[0],
                        "element": link,
                    }
                    return poster_info
        except:
            pass

    except Exception:
        pass

    return poster_info


# ─────────────────────────────────────────────
#  SEARCH FOR HR/RECRUITERS VIA COMPANY PAGE
# ─────────────────────────────────────────────
def search_company_recruiters(driver, company_name, job_title):
    """
    Search LinkedIn for HR/recruiters at the company.
    Returns list of recruiter profiles.
    """
    recruiters = []

    search_queries = [
        f"{company_name} university recruiter",
        f"{company_name} early career recruiter",
        f"{company_name} campus recruiter",
        f"{company_name} intern hiring",
        f"{company_name} HR recruiter",
        f"{company_name} talent acquisition",
    ]

    for query in search_queries[:2]:
        try:
            search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}&origin=GLOBAL_SEARCH_HEADER"
            driver.get(search_url)
            time.sleep(3)

            # Collect people results
            people_cards = driver.find_elements(By.CSS_SELECTOR,
                ".reusable-search__result-container, "
                "li.reusable-search-simple-insight, "
                ".entity-result")

            for card in people_cards[:5]:
                try:
                    # Get profile link
                    link_el = card.find_element(By.CSS_SELECTOR,
                        "a[href*='/in/'], .entity-result__title-text a")
                    href = link_el.get_attribute("href") or ""
                    name = link_el.text.strip()

                    # Get title/headline
                    title = ""
                    try:
                        title_el = card.find_element(By.CSS_SELECTOR,
                            ".entity-result__primary-subtitle, "
                            ".reusable-search-simple-insight__title-text")
                        title = title_el.text.strip()
                    except:
                        pass

                    title_lower = title.lower()
                    is_recruiter = any(w in title_lower for w in [
                        "hr", "recruit", "talent", "hiring", "people",
                        "human resource", "staffing", "acquisition",
                    ])

                    if href and name and is_recruiter:
                        recruiters.append({
                            "name": name,
                            "title": title,
                            "profile_url": href.split("?")[0],
                        })

                except Exception:
                    continue

            if recruiters:
                break

        except Exception:
            continue

        time.sleep(random.uniform(2, 3))

    return recruiters


# ─────────────────────────────────────────────
#  SEND CONNECTION REQUEST
# ─────────────────────────────────────────────
def send_connection_request(driver, profile_url, note):
    """
    Visit a LinkedIn profile and send a connection request with note.
    Returns True if sent successfully.
    """
    try:
        driver.get(profile_url)
        time.sleep(3)

        # Check if already connected
        try:
            msg_btn = driver.find_element(By.CSS_SELECTOR,
                "button[aria-label*='Message'], a[data-control-name='message']")
            if msg_btn and msg_btn.is_displayed():
                print(f"      ✅ Already connected! Can send message directly.")
                return "already_connected"
        except:
            pass

        # Find Connect button
        connect_btn = None
        connect_selectors = [
            "button[aria-label*='Invite'][aria-label*='connect']",
            "button[aria-label*='Connect']",
            "button.pvs-profile-actions__action[aria-label*='connect']",
            "div.pvs-profile-actions button:first-child",
        ]

        for sel in connect_selectors:
            try:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in btns:
                    btn_text = btn.text.strip().lower()
                    if "connect" in btn_text:
                        connect_btn = btn
                        break
                if connect_btn:
                    break
            except:
                continue

        # Try "More" dropdown if Connect not directly visible
        if not connect_btn:
            try:
                more_btn = driver.find_element(By.CSS_SELECTOR,
                    "button[aria-label='More actions'], "
                    "button.artdeco-dropdown__trigger[aria-label*='More']")
                safe_click(driver, more_btn)
                time.sleep(1)

                dropdown_items = driver.find_elements(By.CSS_SELECTOR,
                    "div.artdeco-dropdown__content li, "
                    "div[data-test-dropdown] li")
                for item in dropdown_items:
                    if "connect" in item.text.lower():
                        connect_btn = item
                        break
            except:
                pass

        if not connect_btn:
            print(f"      ⚠️  No Connect button found")
            return False

        # Click Connect
        scroll_into_view(driver, connect_btn)
        safe_click(driver, connect_btn)
        time.sleep(2)

        # Look for "Add a note" button in the modal
        try:
            add_note_btn = None
            note_selectors = [
                "button[aria-label='Add a note']",
                "button.artdeco-button--secondary",
            ]
            for sel in note_selectors:
                try:
                    btns = driver.find_elements(By.CSS_SELECTOR, sel)
                    for btn in btns:
                        if "note" in btn.text.lower() or "add a note" in (btn.get_attribute("aria-label") or "").lower():
                            add_note_btn = btn
                            break
                    if add_note_btn:
                        break
                except:
                    continue

            if add_note_btn:
                safe_click(driver, add_note_btn)
                time.sleep(1)

                # Type the personalized note
                note_field = None
                try:
                    note_field = driver.find_element(By.CSS_SELECTOR,
                        "textarea[name='message'], textarea#custom-message, "
                        "textarea.connect-button-send-invite__custom-message, "
                        "textarea")
                except:
                    pass

                if note_field:
                    note_field.clear()
                    note_field.send_keys(note[:300])
                    time.sleep(0.5)

                # Click Send
                send_btn = None
                try:
                    send_btns = driver.find_elements(By.CSS_SELECTOR,
                        "button[aria-label='Send invitation'], "
                        "button[aria-label='Send now'], "
                        "button.artdeco-button--primary")
                    for btn in send_btns:
                        btn_text = btn.text.strip().lower()
                        if "send" in btn_text:
                            send_btn = btn
                            break
                except:
                    pass

                if send_btn:
                    safe_click(driver, send_btn)
                    time.sleep(2)
                    return True
                else:
                    print(f"      ⚠️  Send button not found")
                    return False
            else:
                # No "Add note" option — send without note
                try:
                    send_btns = driver.find_elements(By.CSS_SELECTOR,
                        "button[aria-label='Send without a note'], "
                        "button[aria-label='Send now'], "
                        "button.artdeco-button--primary")
                    for btn in send_btns:
                        if "send" in btn.text.lower():
                            safe_click(driver, btn)
                            time.sleep(2)
                            return True
                except:
                    pass

        except Exception as e:
            print(f"      ⚠️  Note error: {e}")

        return False

    except Exception as e:
        print(f"      ❌ Connection error: {e}")
        return False


# ─────────────────────────────────────────────
#  SEND MESSAGE (if already connected)
# ─────────────────────────────────────────────
def send_message(driver, profile_url, message):
    """Send a LinkedIn message to someone already connected."""
    try:
        driver.get(profile_url)
        time.sleep(3)

        # Click Message button
        msg_btn = None
        try:
            btns = driver.find_elements(By.CSS_SELECTOR,
                "button[aria-label*='Message'], a[data-control-name='message']")
            for btn in btns:
                if "message" in btn.text.lower():
                    msg_btn = btn
                    break
        except:
            pass

        if not msg_btn:
            return False

        safe_click(driver, msg_btn)
        time.sleep(2)

        # Type message in the chat box
        try:
            msg_box = driver.find_element(By.CSS_SELECTOR,
                "div[role='textbox'], div.msg-form__contenteditable, "
                "div[contenteditable='true']")
            msg_box.click()
            time.sleep(0.5)
            msg_box.send_keys(message)
            time.sleep(0.5)

            # Click Send
            send_btn = driver.find_element(By.CSS_SELECTOR,
                "button.msg-form__send-button, button[type='submit']")
            safe_click(driver, send_btn)
            time.sleep(2)
            return True
        except:
            return False

    except Exception:
        return False


# ─────────────────────────────────────────────
#  MAIN OUTREACH FUNCTION
# ─────────────────────────────────────────────
def run_outreach(driver, config, sent_connections=None):
    """
    Phase 4: LinkedIn Outreach Agent
    1. Search LinkedIn for intern jobs
    2. For each job, find the recruiter/HR
    3. Analyze JD
    4. Send personalized connection request / message
    """
    if sent_connections is None:
        sent_connections = set()

    profile = config.get("profile", {})
    keywords = []
    for agent in config.get("role_agents", []):
        for kw in agent.get("keywords", []):
            if kw not in keywords:
                keywords.append(kw)

    if not keywords:
        keywords = ["Product Management Intern", "Business Intern", "AI Intern"]

    locations = config.get("locations", ["Bangalore"])

    print(f"\n  {'━' * 50}")
    print(f"  🤝 LINKEDIN OUTREACH AGENT")
    print(f"  📋 {len(keywords)} keywords")
    print(f"  🔍 Find HR → Analyze JD → Send personalized connect")
    print(f"  {'━' * 50}")

    total_connections = 0
    total_messages = 0
    max_connections = config.get("max_outreach_per_run", 20)
    outreach_log = []

    for kw in keywords:
        if total_connections >= max_connections:
            print(f"\n  📊 Reached max {max_connections} connections for this run")
            break

        print(f"\n  🔍 Searching: '{kw}'")

        # Search LinkedIn jobs
        for loc in locations[:2]:
            if total_connections >= max_connections:
                break

            search_url = (
                f"https://www.linkedin.com/jobs/search/?"
                f"keywords={quote_plus(kw)}"
                f"&location={quote_plus(loc)}"
                f"&f_TPR=r86400"  # Past 24 hours
                f"&f_E=1"  # Entry level / Internship
                f"&sortBy=DD"  # Most recent
            )

            try:
                driver.get(search_url)
                time.sleep(3)

                # Get job cards
                job_cards = driver.find_elements(By.CSS_SELECTOR,
                    ".jobs-search-results__list-item, "
                    ".job-card-container, "
                    "li.jobs-search-results-list__list-item")

                print(f"    📋 Found {len(job_cards)} job cards")

                for j, card in enumerate(job_cards[:8]):
                    if total_connections >= max_connections:
                        break

                    try:
                        # Click job card to load details
                        scroll_into_view(driver, card)
                        safe_click(driver, card)
                        time.sleep(2)

                        # Extract job info
                        job_title = ""
                        company_name = ""
                        jd_text = ""

                        try:
                            title_el = driver.find_element(By.CSS_SELECTOR,
                                ".job-details-jobs-unified-top-card__job-title, "
                                ".jobs-unified-top-card__job-title, "
                                "h1.t-24, h2.t-24")
                            job_title = title_el.text.strip()
                        except:
                            try:
                                title_el = card.find_element(By.CSS_SELECTOR,
                                    "a.job-card-container__link, strong")
                                job_title = title_el.text.strip()
                            except:
                                continue

                        try:
                            company_el = driver.find_element(By.CSS_SELECTOR,
                                ".job-details-jobs-unified-top-card__company-name, "
                                ".jobs-unified-top-card__company-name, "
                                "a.topcard__org-name-link")
                            company_name = company_el.text.strip()
                        except:
                            company_name = "the company"

                        try:
                            jd_el = driver.find_element(By.CSS_SELECTOR,
                                ".jobs-description__content, "
                                ".jobs-box__html-content, "
                                ".jobs-description-content")
                            jd_text = jd_el.text
                        except:
                            jd_text = ""

                        print(f"\n    [{j+1}] 📌 {job_title[:50]} @ {company_name[:25]}")

                        # Analyze JD
                        themes = analyze_jd(jd_text, job_title, company_name)

                        # Find the poster/recruiter
                        poster = find_job_poster(driver, card)

                        if poster:
                            profile_url = poster["profile_url"]
                            poster_name = poster["name"]

                            if profile_url in sent_connections:
                                print(f"        ⏭️  Already reached out to {poster_name}")
                                continue

                            # Craft AI-personalized note
                            note = craft_connection_note(job_title, company_name, jd_text, poster_name, themes, config)
                            print(f"        👤 Poster: {poster_name}")
                            print(f"        💬 Note: {note[:80]}...")

                            # Send connection
                            result = send_connection_request(driver, profile_url, note)

                            if result == "already_connected":
                                # Send AI-personalized DM
                                msg = craft_direct_message(job_title, company_name, jd_text, poster_name, themes, config)
                                msg_sent = send_message(driver, profile_url, msg)
                                if msg_sent:
                                    total_messages += 1
                                    print(f"        ✅ Message sent to {poster_name}")
                                sent_connections.add(profile_url)
                            elif result:
                                total_connections += 1
                                sent_connections.add(profile_url)
                                print(f"        ✅ Connection request sent! ({total_connections}/{max_connections})")
                                outreach_log.append({
                                    "name": poster_name,
                                    "company": company_name,
                                    "job": job_title,
                                    "action": "connect_request",
                                })
                            else:
                                print(f"        ⚠️  Could not send to {poster_name}")

                            # Navigate back to job search
                            driver.get(search_url)
                            time.sleep(3)

                        else:
                            # No poster found — search for company recruiters
                            print(f"        🔍 No poster found, searching {company_name} recruiters...")
                            recruiters = search_company_recruiters(driver, company_name, job_title)

                            if recruiters:
                                rec = recruiters[0]
                                if rec["profile_url"] not in sent_connections:
                                    note = craft_connection_note(job_title, company_name, jd_text, rec['name'], themes, config)
                                    print(f"        👤 Recruiter: {rec['name']} ({rec['title'][:30]})")
                                    print(f"        💬 Note: {note[:80]}...")

                                    result = send_connection_request(driver, rec["profile_url"], note)
                                    if result and result != "already_connected":
                                        total_connections += 1
                                        sent_connections.add(rec["profile_url"])
                                        print(f"        ✅ Connection sent! ({total_connections}/{max_connections})")
                                    elif result == "already_connected":
                                        msg = craft_direct_message(job_title, company_name, jd_text, rec['name'], themes, config)
                                        send_message(driver, rec["profile_url"], msg)
                                        total_messages += 1
                                        sent_connections.add(rec["profile_url"])
                            else:
                                print(f"        ℹ️  No recruiters found for {company_name}")

                            # Navigate back
                            driver.get(search_url)
                            time.sleep(3)

                        # Rate limit — be gentle with LinkedIn
                        time.sleep(random.uniform(5, 10))

                    except Exception as e:
                        print(f"        ⚠️  Error on job card: {str(e)[:50]}")
                        continue

            except Exception as e:
                print(f"    ❌ Search error: {e}")
                continue

            time.sleep(random.uniform(3, 5))

    # Summary
    print(f"\n  {'━' * 50}")
    print(f"  🎉 OUTREACH COMPLETE!")
    print(f"  🤝 Connection requests sent: {total_connections}")
    print(f"  💬 Messages sent: {total_messages}")
    print(f"  📊 Total reached out: {len(sent_connections)}")
    print(f"  {'━' * 50}")

    if outreach_log:
        print(f"\n  📋 Outreach Log:")
        for entry in outreach_log:
            print(f"    → {entry['name']} @ {entry['company']} ({entry['job'][:30]})")

    return total_connections, total_messages, sent_connections
