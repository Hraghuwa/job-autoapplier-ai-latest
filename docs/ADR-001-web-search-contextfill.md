# ADR-001: Web Search phase rebuilt as "discover → target → fill with ContextFill → close"

**Status:** Accepted (implemented on branch `linkedin-apply-speed`)
**Date:** 2026-10-02
**Deciders:** Harsh (owner)

## Context

Phase 6 (Web Search + ATS Auto-Apply) was reported as "not working, opens the same job again and
again, targets roles that are too senior". A live dry-run reproduction on 2026-10-02 (Chrome 154,
real user config) found:

| # | Flaw | Evidence | Effect |
|---|------|----------|--------|
| F1 | Role matcher compared only the first 5 letters of each keyword word (`manag`, `produ`, `lead`) | 475 Greenhouse postings matched "Consultant / Team Lead / Product Manager", incl. *Director, Engineering*, *Engineering Manager*, *Backend Engineer* | Wrong, senior, tech roles |
| F2 | No seniority, tech/non-tech or location filter before opening a tab | US/UK-only remote jobs, directors opened | Wasted tabs, zero shortlist chance |
| F3 | Every job opened in **two** tabs (`open_in_new_tab` in job_finder + `window.open` in `apply_to_job_url`) | 20 jobs → 40+ tabs | "Same job opened again and again"; Chrome window died |
| F4 | Google is searched twice per run (job_finder mega-search **and** web_search_applier) from an automated browser | 4/4 queries CAPTCHA'd; each CAPTCHA slept 30 s × 37 queries | ~18 min wasted, 0 results |
| F5 | Fit gate (LLM JD analysis) only ran *after* a tab was open and inside the form walker; ranks 4 yrs exp as "mid" | — | Senior roles still opened; career switchers mis-levelled |
| F6 | Tabs never closed; batch "open everything, then fill everything" | — | Can't follow one job end-to-end |
| F7 | Phase failure printed `❌ Finished … Applied: 0` with no exception text | Live run 72d70838 died in 9 s, cause unrecoverable | Undiagnosable failures |
| F8 | The in-repo form filler is weaker than ContextFill (no React-Select/Workday dropdowns, no "ask instead of guess" guard) | — | Bad/hallucinated answers |
| F9 | `auto_submit` is never set by the worker → safety gate always blocks submit | — | Nothing is ever "applied" |

Constraint discovered: branded Google Chrome ≥137 ignores `--load-extension`, so ContextFill
cannot be side-loaded into the agent's normal Chrome. **Chrome for Testing** (downloaded by
Selenium Manager) still honours it — verified: extension loads, ID is deterministic, its
`chrome.storage` and background messaging are scriptable from its own options page.

## Decision

Phase 6 becomes one sequential pipeline:

1. **Discover (fast, no CAPTCHA):** public ATS board APIs (Greenhouse + Lever) fetched in
   parallel, *with JD text* (`?content=true` / `descriptionPlain`). Google is a secondary source
   behind a circuit breaker: the first CAPTCHA/sign-in wall stops Google for the run.
2. **Target (rules, then AI):** `agents/job_targeting.py` rejects a posting before any tab opens if
   - title doesn't contain every significant word of a target keyword (whole words, no stems),
   - level is above the user's target (default **entry/associate** — `target_seniority` pref),
   - it's a tech role and the profile isn't technical,
   - location is outside the user's locations (remote must not be US/UK/EU-only).
   Survivors with JD text then go through the existing LLM fit gate
   (`apply_decision.should_apply`, jd_analyser + fit_scorer) — fail-open.
3. **Apply, one job at a time:** open the job in one tab → click Apply → **ContextFill fills the
   form** (profile + resume seeded from the user's JobAgent profile; Groq if a key exists, else
   local Ollama) → submit through `safety_gate` → **close the tab** → next job.
   A tab is left open only when the user must act (ContextFill has open questions, or
   `auto_submit` is off). If ContextFill can't load, the old smart_form_filler path is used.
4. Dedup by normalised URL across the run + tracker; one tab per job.

## Options Considered

### A. Patch the existing Google-first flow
| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Reliability | Poor — Google CAPTCHAs automated Chrome on the first query |
| Fill quality | Unchanged (smart_form_filler) |

### B. Board-API-first + rule/AI targeting + ContextFill per job (chosen)
| Dimension | Assessment |
|---|---|
| Complexity | Medium (2 new modules, phase 6 rewritten) |
| Reliability | High for discovery (plain HTTPS JSON); fill quality = ContextFill's |
| Speed | Parallel discovery in seconds; fill ≈ seconds with Groq, ~2 min/form with Ollama |
| Cost | Free (Groq free tier / local Ollama) |

**Cons:** needs Chrome for Testing (≈150 MB one-time download by Selenium Manager); board APIs only
cover companies on Greenhouse/Lever (company list must keep growing).

### C. Paid job-search API (SerpAPI / Google Jobs API)
Best coverage of company sites, but paid per query and another key to manage. Revisit if B's
coverage is too thin.

## Which sites actually get an entry-level, non-tech candidate hired (India)

| Type | Examples | How the agent covers it |
|---|---|---|
| Mass job boards | Naukri, LinkedIn, Indeed, foundit | LinkedIn phase; Naukri phase (needs login) |
| Fresher/early-career boards | Internshala (jobs too, not only internships), Unstop, Apna, WorkIndia | Internshala / Unstop phases |
| Startup boards | Wellfound, Cutshort, Instahyre | Wellfound phase |
| Company ATS pages | Greenhouse, Lever, Ashby, Workday, SmartRecruiters | **This phase** (board APIs) |
| Google Forms (campus/startup drives) | docs.google.com/forms | Form-fill phase |

For ops-background candidates, the highest-yield titles are associate/analyst/executive level:
*Business Analyst, Operations Associate/Analyst, Associate Product Manager, Category Associate,
Supply Chain Analyst, Retail/Store Operations Executive, Program Associate, Consulting Analyst.*
"Team Lead" and "Product Manager" are above the target level and will be filtered out.

## Consequences

- Easier: one job = one tab = one log trail; skips print a reason (`⏭ …`) the UI already shows.
- Easier: phase failures now log the exception.
- Harder: ContextFill runs inside Chrome for Testing, not the user's Chrome (separate profile;
  Google/LinkedIn logins there are separate).
- Revisit: add Ashby/SmartRecruiters/Workday board APIs and more company slugs; frontend control
  for `target_seniority` and `auto_submit`.

## Action Items
1. [x] `agents/job_targeting.py` — whole-word role match, level, tech, location rules (+ tests)
2. [x] `agents/contextfill_bridge.py` — load, seed, fill a tab, close it
3. [x] Board APIs in parallel with JD text; Google circuit breaker
4. [x] Phase 6 rewritten as the sequential pipeline; one tab per job
5. [x] Exception text in phase-failure log line
6. [x] Worker passes `target_seniority`, `auto_submit`, `contextfill_dir` prefs
7. [ ] User: add a Groq key (fast fills) and update role keywords to entry-level titles
8. [ ] User: turn on `auto_submit` only once fills look right
