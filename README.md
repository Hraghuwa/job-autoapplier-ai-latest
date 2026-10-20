# JobAgent — AI Job-Search Autopilot

JobAgent finds relevant jobs, fills and submits applications in a real browser, tailors your CV per job, and tracks everything through to interview prep and follow-ups. It ships as a web app (Next.js + FastAPI), a Celery browser-agent worker, a Claude MCP server, and a Chrome form-fill extension.

> **Safety model:** every apply passes a *fit gate* (skip poor matches), per-platform rate limits, a 90-day dedup skiplist and an adaptive human-like delay. Tabs can be left open for your review before submit.

---

## Contents
1. [Architecture](#architecture)
2. [Quick start](#quick-start)
3. [Features](#features)
4. [Agent phases](#agent-phases)
5. [Backend API](#backend-api)
6. [Backend services](#backend-services-backendservices)
7. [Agent modules](#agent-modules-agents)
8. [Frontend pages](#frontend-pages)
9. [MCP server (Claude)](#mcp-server-claude)
10. [Chrome extension](#chrome-extension)
11. [Plans & billing](#plans--billing)
12. [Configuration](#configuration)
13. [Tests, deploy & docs](#tests-deploy--docs)

---

## Architecture

```
Next.js frontend ──REST/WebSocket──▶ FastAPI backend ──▶ Postgres / SQLite
                                         │  enqueue
                                         ▼
                                  Redis ─▶ Celery worker (queue: agents)
                                         │  spawns per-phase subprocess
                                         ▼
                           agents/*  (Selenium / undetected-chromedriver)
                                         │ LLM calls
                                         ▼
                      llm_router: Ollama → Groq → Gemini  (never raises)
```

- **Live progress:** the worker prints agent lines → classified into events → pushed over Redis pub/sub to the `/ws/{user_id}` WebSocket.
- **Isolation:** each phase runs in its own subprocess (`agents/run_phase_subprocess.py`) because the appliers use a module-global `CONFIG`.
- **Resilience:** `agent_supervisor` auto-starts a worker, fails stale runs, and exposes a health check. Celery Beat fires saved cron schedules every 5 min.

## Quick start

Requires Python 3.9+, Node 18+, Redis, Google Chrome.

```bash
bash start.sh          # generates backend/.env, seeds DB + admin, starts Redis, API (:8000), worker, frontend (:3000)
```

Manual:
```bash
pip install -r requirements.txt
cp backend/.env.example backend/.env       # set SECRET_KEY, FERNET_KEY, GEMINI_API_KEY ...
python scripts/seed_local.py
uvicorn backend.main:app --port 8000
celery -A backend.workers.celery_app worker -Q agents,default   # or ./start_worker.sh
celery -A backend.workers.celery_app beat                        # scheduled runs
cd frontend && npm install && npm run dev
```
Then: register → **Onboarding** (upload resume, set preferences, add platform credentials) → **Automation** → run.

Standalone CLI (no web app): fill `agents/config.py`, then `python agents/main.py` or `python agents/run_all_phases.py`.

---

## Features

| Area | What it does |
|---|---|
| **Resume onboarding** | Upload PDF → SHA-256 dedup → Gemini parses into structured profile (summary, skills, experience, education). |
| **Auto-apply** | LinkedIn Easy Apply, Internshala, Wellfound, Naukri, Unstop, and any company/ATS page (Lever, Greenhouse, Workday, generic). |
| **Job discovery** | Google mega-search, platform scrapers, career-page crawler, public board APIs, and JobSpy (LinkedIn/Indeed/Naukri/Google Jobs). |
| **Smart form filling** | Label→answer rules, an `autofill_bank` of your reusable answers, then LLM fallback; handles text, number, textarea, dropdown, radio, checkbox, resume upload, multi-step forms, Google Forms/Typeform. |
| **Fit gate** | Scores each JD against your profile (title match, must-have skills, seniority, your real callback rate) and skips weak matches. |
| **CV tailoring** | JD → structured signature → tailored, hallucination-guarded, ATS-safe PDF (cached per JD + profile version). |
| **Cover notes** | JD-aware "why this role" note with a reviewer pass; static fallback. |
| **AI Missions** | Portal scan → saved target companies/boards → agent applies to them one tab at a time. |
| **Career-Ops** | A–G offer evaluation, comparison, negotiation scripts, STAR story bank, skill gaps, follow-ups, outcome detection from Gmail. |
| **Tracking** | Kanban pipeline, analytics, response rates by resume/archetype, interview prep per application. |
| **Scheduling** | Cron schedules for runs (Pro). |
| **Knowledge graph** | Visual graph of your profile/applications with persisted node positions. |
| **Admin** | User/plan management, revenue, active agents, platform health, metrics. |
| **Payments** | Razorpay (INR) and Stripe (USD) with signed webhooks. |

---

## Agent phases

Run via `POST /agents/run` with a list of phases (filtered by plan, checked against stored credentials).

| # | Phase | Entry |
|---|---|---|
| 1 | LinkedIn Easy Apply (cookies or password) | `run_phase1.py` |
| 2 | Internshala | `orchestrator.run_internshala_phase` |
| 3 | Wellfound | `orchestrator.run_wellfound_phase` |
| 4 | Naukri | `orchestrator.run_naukri_phase` |
| 5 | Unstop | `orchestrator.run_unstop_phase` |
| 6 | Web search (Google + ATS pages, 30+ boards) | `orchestrator.run_web_search_phase` |
| 7 | Auto-fill every open tab | `orchestrator.run_form_fill_phase` |

Pause is honoured cooperatively (`agent_stop.should_stop`, DB/Redis flag polled by the subprocess).

---

## Backend API

FastAPI app in `backend/main.py`. All routes except auth/health/webhooks need a JWT Bearer token. Also: `GET /health`, `WS /ws/{user_id}`.

**`/auth`** — `POST /register`, `POST /login`, `POST /refresh`, `GET /me`, `POST /promote-self` (bootstrap admin with secret).

**`/onboarding`** — `POST /resume` (upload+parse), `POST /preferences`, `POST|GET /credentials` (Fernet-encrypted), `GET /credentials-status`, `GET /test/{platform}`, `POST /autofill` (autofill bank), `POST|GET|DELETE /linkedin-cookies` (+`-status`), `GET /status`.

**`/agents`** — `POST /run`, `GET /healthcheck`, `GET /preflight`, `GET /status/{run_id}`, `GET /runs`, `POST /pause/{run_id}`, `POST|GET /schedule`, `GET /runs/{run_id}/logs`, `POST /runs/{run_id}/analyze` (LLM diagnosis of a run).

**`/jobs`** — `GET ""` (list/filter), `GET /analytics`, `GET /{id}`, `PATCH /{id}/status` (kanban move + email notice), `GET /{id}/interview-prep`.

**`/applications`** — `GET /response-rates/by-resume`, `GET /response-rates/by-archetype`.

**`/resumes`** — CRUD, `POST /{id}/duplicate`, and section CRUD + `PUT /{id}/sections/reorder` for the resume builder.

**`/ai`** — `GET /health`, `POST /enhance-summary`, `/enhance-bullet`, `/generate-bullets`, `/cover-letter`, `/cover-letter/free-preview`.

**`/career-ops`** — `POST /evaluate`, `GET /evaluations`, `POST /compare`, `POST /tailor-cv` (+`/apply`, `/undo`), story bank (`GET|POST /story-bank`, `DELETE /story-bank/{sid}`), `POST /negotiation`, `POST /scan`, mission targets (`GET|POST /mission-targets`, `DELETE /mission-targets/{company}`), `POST /project-eval`, `/training-eval`, `/deep-research`, `/patterns`, `/contact-strategy`, follow-ups (`POST /followup`, `GET /followups/due`, `GET /followups/{app_id}`), `GET /skill-gaps`, `POST /skill-gaps/plan`, `POST /outcomes/gmail-scan`, `POST /outcomes/apply`, `GET /health`.

**`/users`** — `GET|PATCH /profile`, `POST|DELETE /gemini-key`, `POST|DELETE /groq-key` (bring-your-own keys), `GET /api-keys`, `GET /usage`, `GET /quota`, `GET /referral`, `DELETE /account`.

**`/payments`** — `GET /plans`, `GET /config`, Razorpay (`/razorpay/create-order|verify|webhook`), Stripe (`/stripe/create-session|webhook`), legacy `/create-order`, `/verify`.

**`/graph`** — `GET ""`, `GET /stats`, `PUT|DELETE /positions`.

**`/bugs`** — `POST /report`, `GET /list`.

**`/admin`** (admin only) — `GET /users`, `PATCH /users/{id}/plan`, `POST /impersonate/{id}`, `GET /revenue`, `/agents/active`, `/platform-health`, `/metrics`.

---

## Backend services (`backend/services/`)

| Module | Responsibility |
|---|---|
| `agent_supervisor` | Redis/worker checks, auto-spawn worker, recover & fail stale runs, watchdog loop, `healthcheck` (selenium, Chrome, Ollama). |
| `apply_decision` | `should_apply` gate, `report_job` (structured line the worker turns into an Application), `rate_ok` / `rate_register`. |
| `fit_scorer` | `score_fit`: title match, must-have coverage, seniority fit, ±10 adjustment from your own callback rate. |
| `jd_analyser` | JD → `JDSignature` with a hallucination filter; cached by JD hash. |
| `resume_tailor` | Produces a `TailoredResume`; every bullet traces to a source bullet; safe untailored fallback. |
| `resume_pdf` | ReportLab ATS-safe PDF render + `parse_problems` parseability check. |
| `tailored_resume_store` | `get_or_build` cache keyed by (user, JD hash, profile version). |
| `resume_resolver` | Picks tailored PDF or falls back to the static resume. |
| `resume_parser` / `gemini_service` | Save + dedup + parse resume; match score, cover letter, interview prep. |
| `cover_note` | JD-aware note + reviewer pass; `resolve_cover_note`. |
| `rate_limits` | In-memory and Redis per-user/per-platform limiters with failure counts. |
| `backoff` | Jittered, ban-aware inter-apply delay (`polite_sleep`, `delay_for`). |
| `skiplist` | 90-day apply cooldown; `SkipSet` backs the appliers' `applied_urls`. |
| `plan_gate` | Plan limits, platform access, monthly AI-token refill/consume. |
| `followthrough` | Follow-ups due, skill gaps, Gmail (IMAP) outcome classification — proposals only, never auto-applied. |
| `response_rates` | Callback rates per tailored resume / archetype. |
| `run_metrics` / `llm_usage` | Per-platform run metrics; per-call token & cost capture. |
| `linkedin_cookies` | Parse Cookie-Editor export, validate `li_at`, snapshot refreshed cookies. |
| `crypto_service` | Fernet encrypt/decrypt for credentials. |
| `untrusted` | `fence` / `looks_injected` — prompt-injection defence for scraped text. |
| `email_service` | Resend emails: welcome, run complete, status change, receipt. |
| `graph_service`, `tracking_service` | Knowledge graph and application tracking helpers. |

Workers: `workers/agent_tasks.py` (`run_phase_task`, `check_schedules`, quota checks, event classification, stop signalling), `workers/celery_app.py` (queues + Beat).

---

## Agent modules (`agents/`)

| Module | Role |
|---|---|
| `orchestrator.py` | Per-phase runners, Chrome driver creation (server mode, profiles), teardown. |
| `linkedin_applier.py` | Cookie/password login, job-card loop, Easy Apply modal filling, external-apply handling, title relevance. |
| `internshala_applier.py`, `other_platforms.py` (Unstop, Naukri), `wellfound_applier.py` | Login, paginated search, apply, per-site cover notes, CAPTCHA detection. |
| `web_search_applier.py` | Google job search → ATS detection (Lever/Greenhouse/Workday/generic) → apply, one job/tab at a time via ContextFill. |
| `job_finder.py` | Mega-search, platform tab search, career-page crawl, board APIs, JobSpy bridge. |
| `jobspy_fetch.py` | Separate-interpreter (Py ≥3.10) JobSpy runner returning JSON postings. |
| `job_targeting.py` | Pure rules to reject postings pre-open (level, tech/non-tech, location). |
| `smart_form_filler.py` | Field matching & filling engine for all input types, resume upload, fit gate, multi-step walker. |
| `google_form_filler.py` | Google Forms, Typeform and generic external forms. |
| `contextfill_bridge.py` / `contextfill_page.py` | Drive the ContextFill extension / run its scanner in-page, mapping fields via the LLM. |
| `agent_vision.py` | Gemini vision: screenshot → find Apply button, analyse forms, read JD. |
| `agent_stop.py` | Cooperative pause. |
| `run_phase_subprocess.py`, `run_phase1.py`, `run_all_phases.py`, `main.py`, `run_wellfound.py` | Subprocess entry, CLI runners, timed multi-phase run. |
| `url_utils.py`, `config.py` | URL normalisation; standalone CLI config. |

`llm_router.py` (root) — role-based routing (`form_fill`, `writer`) across Ollama → Groq → Gemini; returns `None`/`""` instead of raising.

---

## Frontend pages

Next.js App Router, Tailwind + shadcn/ui (`frontend/app`).

| Route | Purpose |
|---|---|
| `/` | Landing page. |
| `/login`, `/register` | Auth. |
| `/onboarding` | Resume upload, preferences, guided setup. |
| `/dashboard` | Stats, recent applications, live agent feed. |
| `/automation` | Pick phases, start/pause runs, schedules, live logs and toasts. |
| `/credentials` | Platform logins, LinkedIn cookies, autofill answers, API keys. |
| `/jobs`, `/jobs/[id]` | Drag-and-drop kanban, search, detail with interview prep. |
| `/analytics` | Funnel and response-rate charts. |
| `/career-ops` | Tabs: Evaluate, Tailor, Scan, Story Bank, Negotiate, and more. |
| `/graph` | Interactive knowledge graph. |
| `/settings`, `/settings/billing` | Profile, keys, usage, plans and payments. |
| `/admin` | Admin console. |

Shared: `lib/api.ts` (axios + JWT), `lib/auth.ts`, `lib/ws.ts` (live events), `BugReportButton`, `TokenBadge`, `GraphMiniMap`, error boundary.

---

## MCP server (Claude)

`mcp_server/jobagent_mcp.py` is a stdio MCP server so Claude can run your job search. Run `python mcp_server/jobagent_mcp.py login` once to store credentials.

Tools: `get_profile`, `set_job_targets`, `scan_portals`, `save_mission_targets`, `list_mission_targets`, `remove_mission_target`, `tailor_cv`, `apply_cv_tailoring`, `undo_cv_tailoring`, `launch_mission`, `mission_status`, `mission_logs`, `stop_mission`, `list_applications`, `record_outcome`, `interview_prep`, `followups_due`, `draft_followup`, `skill_gaps`, `study_plan`, `evaluate_offer`.

Claude Code slash commands live in `.claude/commands/`: `job-setup`, `job-apply`, `job-daily`, `job-weekly`, `job-interview`.

## Chrome extension

`chrome_extension/` (Manifest V3, "Smart Fill"): popup stores your profile in `data.js`; `content.js` fills the active tab's application form. Build with `python build_extension.py`.

---

## Plans & billing

| | Free | Pro | Team |
|---|---|---|---|
| Platforms | LinkedIn | All 6 | All 6 |
| Apply credits/day | 20 | Unlimited | Unlimited |
| AI tokens/month | 50 | 2,000 | 5,000 |
| Web search, cover letters, scheduling, analytics, kanban | – | ✔ | ✔ |
| Tabs | 20 | 100 | 100 |

Pro: ₹499/mo or ₹3,999/yr (Razorpay), $9.99/mo or $79.99/yr (Stripe). Apply-credit packs are sold one-off. Users can bring their own Gemini/Groq keys to avoid spending operator tokens.

## Configuration

Set in `backend/.env` (templates: `backend/.env.example`, `.env.prod.example`, `frontend/.env.local.example`).

| Variable | Purpose |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | Storage / queue (SQLite local, Postgres prod). |
| `SECRET_KEY`, `FERNET_KEY` | JWT signing / credential encryption. `SECRET_KEY` is derived from `FERNET_KEY` if unset. |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OLLAMA_HOST` (+ `*_FORM_MODEL`, `*_WRITER_MODEL`), `JOBAGENT_LLM_ORDER` | LLM providers and routing. |
| `CHROME_BIN`, `CHROMEDRIVER_PATH`, `JOBAGENT_SERVER_MODE` | Browser setup / headless server mode. |
| `JOBSPY_PYTHON`, `CONTEXTFILL_DIR`, `CONTEXTFILL_CHROME` | JobSpy interpreter, ContextFill extension. |
| `JOBAGENT_INPROC_PHASE`, `DISABLE_AGENT_SUPERVISOR`, `AGENT_WORKER_CONCURRENCY`, `AGENT_STALE_TIMEOUT_MIN`, `AGENT_WATCHDOG_INTERVAL_S` | Worker behaviour. |
| `ADMIN_BOOTSTRAP_SECRET` | Allows `/auth/promote-self`. |

Payment (Razorpay/Stripe) and email (Resend) keys are read by their routers/services.

## Tests, deploy & docs

- **Tests:** `pytest tests/` (API, auth, security, dedup, field mapping, safety gate, payments webhook, career pipeline, browser); frontend: `cd frontend && npm test`. CI: `.github/workflows/ci.yml`.
- **Deploy:** `Procfile`/`railway.json`/`nixpacks.toml` (Railway), `docker-compose[.prod].yml`, `backend/Dockerfile[.worker]`, `frontend/vercel.json`, `Caddyfile`. The worker needs Chrome — see `docs/WORKER.md`.
- **More docs:** `docs/` — `ADR-001-web-search-contextfill.md`, `CAREER_OPS_INTEGRATION.md`, `DATABASE.md`, `DEPLOY_ORACLE.md`, `C2_CONCURRENCY_PLAN.md`, `SYSTEM_AUDIT.md`, `SECURITY_INCIDENT_C1.md`; roadmap in `PLAN.md`, `TODO.md`.

> ⚠️ Automating applications may violate some platforms' terms of service. Use sensible limits, keep your credentials private, and review what is submitted.
