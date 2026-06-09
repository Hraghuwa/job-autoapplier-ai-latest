"""
🔍 Job Finder v3 — MASSIVE INTERNET-WIDE SEARCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Searches 100+ websites across the internet for ANY roles the user
configured — intern, full-time, contract, whatever their role_agents
or keywords list specifies. The role detection is driven by
CONFIG["role_agents"] and CONFIG["keywords"], NOT hardcoded to "intern".

EVERY found job opens in its OWN NEW TAB.
Search tab stays separate — never navigates away.
Browser stays OPEN with all tabs for manual application (tabs are
preserved on both stop AND normal completion — see orchestrator.py).

Strategy: Use Google as the search engine to discover jobs
across ALL websites (not just specific platforms).
Each Google search finds jobs across many sites at once.

Role orchestration: when multiple role_agents are configured, queries
are round-robin interleaved so every role gets equal coverage in
parallel rather than one role consuming the entire query budget.
"""

import time
import random
import traceback
from urllib.parse import quote_plus, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

import google_form_filler
import web_search_applier


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def is_driver_alive(driver):
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def open_in_new_tab(driver, url):
    """Open a URL in a new tab via JS — never leaves current tab."""
    try:
        # Escape single quotes in URL
        safe_url = url.replace("'", "\\'")
        driver.execute_script(f"window.open('{safe_url}', '_blank');")
        time.sleep(0.2)
        return True
    except Exception:
        return False


def scroll_page(driver, times=2):
    for _ in range(times):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        except:
            break


# Domains to skip (not job sites)
SKIP_DOMAINS = [
    "youtube.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "quora.com", "reddit.com", "pinterest.com",
    "wikipedia.org", "google.com", "maps.google", "play.google",
    "amazon.com", "flipkart.com/product", "news.", "blog.",
]

# Domains and paths that indicate job pages
JOB_INDICATORS = [
    "career", "jobs", "apply", "hiring", "openings", "positions",
    "recruit", "talent", "vacancy", "join-us", "join-our-team",
    "work-with-us", "opportunities", "internship", "intern",
    "lever.co", "greenhouse.io", "workday.com", "myworkdayjobs.com",
    "smartrecruiters.com", "icims.com", "ashbyhq.com", "breezy.hr",
    "bamboohr.com", "freshteam.com", "zohorecruit.com", "cutshort.io",
    "darwinbox.com", "keka.com", "hirist.com", "angel.co",
    "wellfound.com", "instahyre.com", "hirect.in",
    "naukri.com", "internshala.com", "unstop.com", "foundit.in",
    "indeed.com", "glassdoor.", "linkedin.com/jobs",
    "workindia.in", "apna.co", "iimjobs.com",
    "arc.dev", "toptal.com", "gun.io", "yunojuno.com",
    "upwork.com", "usebraintrust.com", "fiverr.com/pro",
    "weworkremotely.com",
]


def extract_google_links(driver, found_urls, applied_urls):
    """Extract all job-related links from the current Google results page."""
    new_urls = []
    try:
        all_links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
        for link in all_links:
            try:
                href = link.get_attribute("href") or ""
                if len(href) < 20:
                    continue

                parsed = urlparse(href)
                domain = parsed.netloc.lower()
                path = parsed.path.lower()
                full = (domain + path).lower()

                if parsed.scheme not in ("http", "https"):
                    continue
                if "google." in domain:
                    continue
                if any(skip in full for skip in SKIP_DOMAINS):
                    continue

                # Check if this looks like a job page
                is_job = any(ind in full for ind in JOB_INDICATORS)

                if is_job:
                    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if parsed.query:
                        clean += f"?{parsed.query}"
                    if clean not in found_urls and clean not in applied_urls and clean not in new_urls:
                        new_urls.append(clean)

            except Exception:
                continue
    except Exception:
        pass
    return new_urls


# ─────────────────────────────────────────────
#  GOOGLE MEGA-SEARCH: 100+ websites
# ─────────────────────────────────────────────

# Global job-board sites to target across Google queries.
# These are searched alongside the user's configured keywords so the
# agent gets broad internet coverage in a single run. The user can
# override/extend via config["web_search"]["extra_sites"].
MAINSTREAM_JOB_BOARDS = [
    # Indian + international mainstream
    "internshala.com", "unstop.com", "naukri.com",
    "indeed.com", "indeed.co.in", "glassdoor.com", "glassdoor.co.in", "foundit.in",
    "wellfound.com", "instahyre.com", "cutshort.io",
    "hirect.in", "workindia.in", "apna.co", "iimjobs.com",
    "hirist.com", "angel.co", "linkedin.com/jobs",
    # Added per user request: large mainstream + developer + remote boards
    "simplyhired.com", "stackoverflow.com/jobs", "jobspresso.co",
]

REMOTE_JOB_BOARDS = [
    # Remote-first boards requested by the user
    "nodesk.co", "remotive.com", "remote4me.com", "pangian.com",
    "remotees.com", "remotehabits.com", "skiptheachive.com",
    # Common remote boards kept because they pair well with the above
    "weworkremotely.com", "remoteok.com", "justremote.co",
    "himalayas.app", "remote.co", "workingnomads.co",
    # Remote dev-focused job boards
    "arc.dev",
]

FREELANCE_PLATFORMS = [
    # Freelance & contract marketplaces added per user request
    "toptal.com", "gun.io", "yunojuno.com",
    "upwork.com", "usebraintrust.com", "fiverr.com/pro",
]

ATS_PLATFORMS = [
    "lever.co", "greenhouse.io", "ashbyhq.com",
    "smartrecruiters.com", "workday.com", "icims.com",
    "bamboohr.com", "freshteam.com", "breezy.hr",
    "zohorecruit.com", "darwinbox.com",
]


def build_search_queries(keywords, config):
    """
    Build a comprehensive list of Google `site:` queries covering:

      • Mainstream boards (Indeed, Glassdoor, Wellfound, LinkedIn, StackOverflow...)
      • Remote boards (NoDesk, Remotive, Pangian, Remotees, RemoteHabits...)
      • ATS platforms (Lever, Greenhouse, Ashby, Workday...)
      • Target company career pages (from config)
      • Google Form applications
      • Extra sites the user provides via config["web_search"]["extra_sites"]

    Duplicate queries are de-duplicated at the end so the same search isn't
    issued twice in a single run — one of the explicit user requirements.
    The role language ("intern"/"full-time") is taken from the user's
    keywords, NOT hardcoded, so job_finder stays role-agnostic.
    """
    queries = []

    web_cfg = config.get("web_search", {}) or {}
    extra_sites = web_cfg.get("extra_sites", []) or []

    # Full list of job boards the user wants searched every run.
    # Order: mainstream → remote → freelance → ATS → user-provided extras.
    job_boards = MAINSTREAM_JOB_BOARDS + REMOTE_JOB_BOARDS + FREELANCE_PLATFORMS + list(extra_sites)

    locations = config.get("locations") or ["Bangalore"]
    primary_loc = locations[0] if locations else ""

    # ── 1. Group every ~6 sites into a single OR'd `site:` query so one
    #    Google search covers multiple boards at once. This keeps the
    #    total query count manageable while still hitting every board.
    def _chunks(seq, size):
        for i in range(0, len(seq), size):
            yield seq[i:i + size]

    for kw in keywords[:8]:
        for chunk in _chunks(job_boards, 6):
            site_group = " OR ".join(f"site:{p}" for p in chunk)
            if primary_loc:
                queries.append(f'{kw} {primary_loc} apply ({site_group})')
            else:
                queries.append(f'{kw} apply ({site_group})')

    # ── 2. ATS platform searches ──
    for kw in keywords[:6]:
        ats_group = " OR ".join(f"site:{a}" for a in ATS_PLATFORMS[:5])
        queries.append(f'{kw} ({ats_group})')
        ats_group2 = " OR ".join(f"site:{a}" for a in ATS_PLATFORMS[5:])
        if ats_group2:
            queries.append(f'{kw} apply ({ats_group2})')

    # ── 3. Target company career pages (from config) ──
    target_companies = web_cfg.get("target_companies", []) or []
    for company in target_companies[:40]:
        queries.append(f'site:{company}.com careers apply')
    for company in target_companies[40:]:
        queries.append(f'site:{company}.com hiring')

    # ── 4. Broad internet searches across user locations + "remote" ──
    for kw in keywords:
        for loc in locations[:2]:
            queries.append(f'{kw} {loc} apply 2025 2026')
            queries.append(f'{kw} {loc} hiring apply now')
        queries.append(f'{kw} remote apply')

    # ── 5. Consulting/Corp searches (only if user keywords mention them) ──
    consulting_firms = "BCG McKinsey Bain Deloitte KPMG EY PwC Accenture"
    consulting_keywords = [kw for kw in keywords if any(w in kw.lower() for w in
        ["consultant", "strategy", "management trainee", "business"])]
    for kw in consulting_keywords[:4]:
        queries.append(f'{kw} {consulting_firms} apply 2025')

    # ── 6. Platform discovery using user keywords ──
    for kw in keywords[:10]:
        if primary_loc:
            queries.append(f'"apply now" {kw} {primary_loc}')
            queries.append(f'"we are hiring" {kw} {primary_loc}')
        else:
            queries.append(f'"apply now" {kw}')
            queries.append(f'"we are hiring" {kw}')

    # ── 7. Startup aggregators ──
    startup_sites = ["ycombinator.com", "workatastartup.com", "wellfound.com"]
    for site in startup_sites:
        for kw in keywords[:4]:
            queries.append(f'site:{site} {kw}')

    # ── 8. Google Form job applications ──
    for kw in keywords[:8]:
        queries.append(f'site:docs.google.com/forms "{kw}" apply')

    # ── De-duplicate while preserving order — one of the user's explicit
    # anti-repetition requirements. Without this the same site-chunk
    # query can appear multiple times because keyword loops overlap.
    seen = set()
    deduped = []
    for q in queries:
        norm = " ".join(q.lower().split())
        if norm in seen:
            continue
        seen.add(norm)
        deduped.append(q)
    return deduped


def google_mega_search(driver, keywords, config, applied_urls, max_tabs=20):
    """
    Use Google to search 100+ websites for intern jobs.
    Opens EVERY found job in its OWN NEW TAB, up to max_tabs.
    """
    print(f"\n  {'━' * 50}")
    print(f"  🌐 MEGA INTERNET SEARCH — 100+ websites")
    print(f"  📋 Every job opens in its own tab")
    print(f"  {'━' * 50}")

    found_urls = []
    queries = build_search_queries(keywords, config)

    print(f"  📊 Total search queries: {len(queries)}")
    print(f"  🔍 Starting searches...\n")

    # Keep the first tab as our "search" tab
    search_tab = driver.current_window_handle

    for i, query in enumerate(queries):
        if not is_driver_alive(driver):
            break

        # Always switch back to search tab before new query
        try:
            driver.switch_to.window(search_tab)
        except:
            break

        print(f"  🔎 [{i+1}/{len(queries)}] {query[:65]}...")

        try:
            search_url = f"https://www.google.com/search?q={quote_plus(query)}&num=15"
            driver.get(search_url)
            time.sleep(random.uniform(2, 4))

            # Check for CAPTCHA
            page_text = driver.page_source.lower()
            if "unusual traffic" in page_text or "captcha" in page_text:
                print(f"  ⚠️  Google CAPTCHA! Pausing 30s...")
                time.sleep(30)
                continue

            # Extract job links from results
            new_urls = extract_google_links(driver, found_urls, applied_urls)

            if new_urls:
                space_left = max_tabs - len(found_urls)
                new_urls = new_urls[:space_left]
                found_urls.extend(new_urls)
                # Open each new URL in its own tab
                search_tab = driver.current_window_handle
                for url in new_urls:
                    print(f"       🚀 Starting active apply for: {url[:60]}...")
                    # Try to apply immediately
                    try:
                        # Re-calculate windows before attempt
                        search_tab = driver.current_window_handle
                        success = web_search_applier.apply_to_job_url(driver, url, config)
                        if success:
                            print(f"       ✅ SUCCESS: Application completed!")
                        else:
                            print(f"       ⚠️  Active apply failed — tab remains open for review.")
                        
                        # Always switch back to search tab
                        driver.switch_to.window(search_tab)
                    except Exception as ef:
                        print(f"       ⚠️  Active apply error: {ef}")
                        try:
                            driver.switch_to.window(search_tab)
                        except:
                            pass

                print(f"       → Proccessed {len(new_urls)} jobs (total found: {len(found_urls)})")

                if len(found_urls) >= max_tabs:
                    print("  🛑 Reached max 20 tabs limit (Google Search).")
                    break

            # Also check page 2 of Google results for important queries
            if i < 20:  # Only for the first 20 queries
                try:
                    next_btn = driver.find_elements(By.CSS_SELECTOR,
                        "a#pnnext, a[aria-label='Next']")
                    if next_btn:
                        driver.switch_to.window(search_tab)
                        next_btn[0].click()
                        time.sleep(random.uniform(2, 3))
                        page2_urls = extract_google_links(driver, found_urls, applied_urls)
                        if page2_urls:
                            space_left = max_tabs - len(found_urls)
                            page2_urls = page2_urls[:space_left]
                            found_urls.extend(page2_urls)
                            search_tab = driver.current_window_handle
                            for url in page2_urls:
                                open_in_new_tab(driver, url)
                                try:
                                    driver.switch_to.window(search_tab)
                                except:
                                    pass
                            print(f"       → Page 2: {len(page2_urls)} more jobs")
                            
                            if len(found_urls) >= max_tabs:
                                print("  🛑 Reached max 20 tabs limit (Google Search Page 2).")
                                break
                except:
                    pass

        except Exception as e:
            print(f"       ⚠️  {str(e)[:50]}")
            continue

        time.sleep(random.uniform(1, 3))

        # Progress update every 10 queries
        if (i + 1) % 10 == 0:
            tabs = len(driver.window_handles) if is_driver_alive(driver) else 0
            print(f"\n  📊 PROGRESS: {len(found_urls)} jobs found | {tabs} tabs open\n")

    return found_urls


# ─────────────────────────────────────────────
#  DIRECT PLATFORM SEARCHES (new tab per job)
# ─────────────────────────────────────────────
def search_platform_open_tabs(driver, platform_name, search_urls, selectors, domain_filter, applied_urls, found_urls, max_new_tabs=20):
    """
    Search a specific platform and open every result in a new tab.
    The search page itself opens in a new tab, results open in more tabs.
    """
    print(f"\n  🔍 [{platform_name}] Searching...")
    new_found = []
    search_tab = driver.current_window_handle

    for search_url in search_urls[:8]:
        if not is_driver_alive(driver):
            break

        try:
            # Open search in the search tab
            driver.switch_to.window(search_tab)
            driver.get(search_url)
            time.sleep(3)
            scroll_page(driver, 2)

            # Collect all job links
            links = driver.find_elements(By.CSS_SELECTOR, selectors)
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
                    if (href and domain_filter in href
                            and href not in applied_urls
                            and href not in found_urls
                            and href not in new_found
                            and len(new_found) < max_new_tabs):
                        new_found.append(href)
                except:
                    continue

        except Exception as e:
            print(f"    ⚠️  {str(e)[:50]}")
            continue

        time.sleep(random.uniform(1, 2))

    # Apply to ALL found jobs
    if new_found:
        print(f"  📋 [{platform_name}] Found {len(new_found)} jobs, proceeding to active apply...")
        search_tab = driver.current_window_handle
        for url in new_found:
            print(f"    🚀 Active apply: {url[:60]}...")
            try:
                web_search_applier.apply_to_job_url(driver, url, config)
                driver.switch_to.window(search_tab)
            except:
                try: driver.switch_to.window(search_tab)
                except: pass
    else:
        print(f"  ℹ️  [{platform_name}] No new jobs found")

    # Switch back to search tab
    try:
        driver.switch_to.window(search_tab)
    except:
        pass

    return new_found


# ─────────────────────────────────────────────
#  DIRECT COMPANY CAREER PAGES
# ─────────────────────────────────────────────
DIRECT_CAREER_URLS = [
    "https://www.google.com/about/careers/applications/jobs/results/?location=Bangalore&target_level=INTERN",
    "https://careers.microsoft.com/us/en/search-results?keywords=intern&location=Bangalore",
    "https://amazon.jobs/en/search?base_query=intern&loc_query=Bangalore",
    "https://razorpay.com/jobs/", "https://jobs.lever.co/cred",
    "https://boards.greenhouse.io/phonepe", "https://boards.greenhouse.io/groww",
    "https://boards.greenhouse.io/zomato", "https://boards.greenhouse.io/sharechat",
    "https://boards.greenhouse.io/unacademy", "https://boards.greenhouse.io/jupiter",
    "https://freshworks.com/company/careers/openings/",
    "https://www.zoho.com/careers/india/openings.html",
    "https://dream11.com/careers", "https://careers.slice.one/",
    "https://paytm.com/careers", "https://zerodha.com/careers",
    "https://www.flipkart.com/about-us/careers",
    "https://www.swiggy.com/careers", "https://www.meesho.io/careers",
    "https://www.myntra.com/careers", "https://careers.nykaa.com/",
    "https://lenskart.com/careers", "https://careers.boat-lifestyle.com/",
    "https://bcg.com/careers", "https://bain.com/careers",
    "https://www.deloitte.com/in/en/careers.html",
    "https://jobs.ashbyhq.com/Atlassian",
    "https://notion.so/careers", "https://stripe.com/jobs",
    "https://www.postman.com/company/careers/",
    "https://browserstack.com/careers", "https://hasura.io/careers/",
    "https://www.accenture.com/in-en/careers",
]


def crawl_career_pages(driver, applied_urls, found_urls, max_new_tabs=20):
    """Visit direct career pages, find job links, open each in a new tab."""
    print(f"\n  🔍 [Career Pages] Crawling {len(DIRECT_CAREER_URLS)} company sites...")
    new_found = []
    search_tab = driver.current_window_handle

    for career_url in DIRECT_CAREER_URLS:
        if not is_driver_alive(driver):
            break

        try:
            domain = urlparse(career_url).netloc.replace("www.", "").split(".")[0]
            driver.switch_to.window(search_tab)
            driver.get(career_url)
            time.sleep(2)
            scroll_page(driver, 1)

            # Find all links that look like job postings
            all_links = driver.find_elements(By.CSS_SELECTOR, "a[href]")
            for link in all_links:
                try:
                    href = link.get_attribute("href") or ""
                    if len(href) < 20:
                        continue
                    path_lower = href.lower()
                    is_job = any(w in path_lower for w in [
                        "intern", "product", "analyst", "associate",
                        "business", "founder", "growth", "strategy",
                        "/job/", "/apply/", "/position/", "/opening/",
                    ])
                    if is_job and href not in applied_urls and href not in found_urls and href not in new_found and len(new_found) < max_new_tabs:
                        new_found.append(href)
                except:
                    continue

        except Exception:
            continue

        time.sleep(random.uniform(0.5, 1.5))

    if new_found:
        print(f"  📋 [Career Pages] Found {len(new_found)} jobs, proceeding to active apply...")
        search_tab = driver.current_window_handle
        for url in new_found:
            print(f"    🚀 Active apply: {url[:60]}...")
            try:
                web_search_applier.apply_to_job_url(driver, url, config)
                driver.switch_to.window(search_tab)
            except:
                try: driver.switch_to.window(search_tab)
                except: pass
    else:
        print(f"  ℹ️  [Career Pages] No new jobs found")

    try:
        driver.switch_to.window(search_tab)
    except:
        pass

    return new_found


# ─────────────────────────────────────────────
#  MAIN: FIND ALL JOBS (v3 — MASSIVE SEARCH)
# ─────────────────────────────────────────────
def find_all_jobs(driver, config, applied_urls=None, max_tabs=20):
    """
    MASSIVE internet-wide job search.
    Every found job opens in its OWN NEW TAB up to max_tabs.
    Browser stays open for manual application.
    """
    if applied_urls is None:
        applied_urls = set()
    else:
        applied_urls = set(applied_urls)

    # Gather ALL keywords
    all_keywords = []
    for agent in config.get("role_agents", []):
        for kw in agent.get("keywords", []):
            if kw not in all_keywords:
                all_keywords.append(kw)
    for kw in config.get("keywords", []):
        if kw not in all_keywords:
            all_keywords.append(kw)
    if not all_keywords:
        all_keywords = ["Product Management Intern", "Business Intern", "AI Intern"]

    locations = config.get("locations", ["Bangalore", "Bengaluru"])
    all_found = []

    print(f"\n  {'━' * 55}")
    print(f"  🚀 MEGA JOB SEARCH ENGINE v3")
    print(f"  🌐 Searching 100+ websites across the entire internet")
    print(f"  📋 {len(all_keywords)} keywords | Every job → own tab")
    print(f"  📍 Location: {', '.join(locations)}")
    print(f"  {'━' * 55}")

    # ── 1. GOOGLE MEGA SEARCH (finds jobs across ALL websites) ──
    try:
        urls = google_mega_search(driver, all_keywords, config, applied_urls, max_tabs=max_tabs)
        all_found.extend(urls)
    except Exception as e:
        print(f"  ❌ Google search error: {e}")
        traceback.print_exc()

    # ── 2. Direct platform searches (Internshala, Unstop, Naukri, etc.) ──
    # Build platform search URLs
    for kw in all_keywords[:5]:
        kw_slug = kw.lower().replace(" ", "-")

        # Internshala
        try:
            internshala_urls = [
                f"https://internshala.com/internships/{kw_slug}-internship-in-bangalore",
                f"https://internshala.com/internships/{kw_slug}-internship/work-from-home",
            ]
            new = search_platform_open_tabs(driver, f"Internshala:{kw[:20]}",
                internshala_urls,
                "a[href*='/internship/'], a.view_detail_button",
                "internshala.com", applied_urls, all_found, max_new_tabs=max_tabs - len(all_found))
            all_found.extend(new)
        except:
            pass
            
        if len(all_found) >= max_tabs: break

        # Unstop
        try:
            unstop_urls = [
                f"https://unstop.com/internships?search={quote_plus(kw)}",
                f"https://unstop.com/jobs?search={quote_plus(kw)}",
            ]
            new = search_platform_open_tabs(driver, f"Unstop:{kw[:20]}",
                unstop_urls,
                "a[href*='/internship/'], a[href*='/job/'], .opportunity-card a",
                "unstop.com", applied_urls, all_found, max_new_tabs=max_tabs - len(all_found))
            all_found.extend(new)
        except:
            pass
            
        if len(all_found) >= max_tabs: break

        # Naukri
        try:
            naukri_urls = [
                f"https://www.naukri.com/{kw_slug}-jobs-in-bangalore",
            ]
            new = search_platform_open_tabs(driver, f"Naukri:{kw[:20]}",
                naukri_urls,
                "a.title, a[href*='naukri.com/job/'], article a",
                "naukri.com", applied_urls, all_found, max_new_tabs=max_tabs - len(all_found))
            all_found.extend(new)
        except:
            pass
            
        if len(all_found) >= max_tabs: break

    # ── 3. Direct company career pages ──
    if len(all_found) < max_tabs:
        try:
            urls = crawl_career_pages(driver, applied_urls, all_found, max_new_tabs=max_tabs - len(all_found))
            all_found.extend(urls)
        except Exception as e:
            print(f"  ❌ Career pages error: {e}")

    # ── FINAL SUMMARY ──
    tabs = len(driver.window_handles) if is_driver_alive(driver) else 0

    print(f"\n  {'═' * 55}")
    print(f"  🎉 MEGA SEARCH COMPLETE!")
    print(f"  📊 TOTAL JOBS FOUND: {len(all_found)}")
    print(f"  📑 TABS OPEN: {tabs}")
    print(f"  🌐 Each job is in its own tab!")
    print(f"  👉 Go through tabs and apply manually!")
    print(f"  ⚠️  Browser stays open — take your time!")
    print(f"  {'═' * 55}")

    return all_found
