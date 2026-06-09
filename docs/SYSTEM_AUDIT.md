# SYSTEM AUDIT — Job Auto-Applier AI

> Autonomous full-system audit. Read-only investigation; **no code changed, nothing deployed.**
> Repo: https://github.com/Hraghuwa/job-autoapplier-ai-latest.git
> Audit started: 2026-06-08 · Pass 1 (of an ongoing /loop). Status: **investigation, not yet acted on.**

---

## 0. Ingestion status (Phase 0)

| Area | Read | Notes |
|---|---|---|
| Docs (README, PLAN, TODO) | ✅ | PLAN.md is the source of intent (JD→tailored-PDF→apply) |
| Entry points (main.py, backend/main.py) | ✅ | Two-layer system (see §1) |
| Orchestration (workers/agent_tasks.py, agent_supervisor.py) | ✅ | Core run pipeline |
| LLM routing (llm_router.py) | ✅ | Ollama→Groq→Gemini chain |
| Security (crypto_service, config, auth.py, rate_limits) | ✅ | Several findings (§3) |
| Appliers (linkedin/internshala/wellfound/web_search/forms) | ⏳ partial | grep-level only; deep read pending pass 2 |
| Resume pipeline (jd_analyser, resume_tailor, resume_pdf, store) | ⏳ pending | Hallucination guard not yet verified |
| Frontend (Next.js, 24 routes, 22 components) | ⏳ pending | pass 3 |
| Tests (10 files, career_pipeline + api) | ⏳ pending | not yet executed |

**Missing-information report:** no production logs, no metrics dashboard, no historical run data
beyond the committed SQLite snapshots, no error-rate telemetry, no real-world apply-success numbers.
All "success rate / cost / latency" metrics below are therefore **architectural estimates, not measured.**
This is the single biggest gap: the system has no observability to prove it works.

---

## 1. System Understanding & Architecture (Phase 1)

This is **two systems in one repo** sharing the Selenium appliers:

### Layer A — Legacy single-user CLI
`main.py` + root `*.py` (linkedin_applier, job_finder, google_form_filler, web_search_applier…),
driven by a local `config.py`, persistent `chrome_profile/`, tracking in `applied_jobs.json`.
Run with `python main.py`. Single user, single machine.

### Layer B — Multi-tenant SaaS (the real product)
```
Next.js frontend (Vercel)  ──HTTPS/JWT──▶  FastAPI backend (Railway)
   24 app routes                              13 routers, async SQLAlchemy
   WebSocket live feed   ◀──Redis pub/sub──   Celery worker(s)  ─spawns▶ Chrome/Selenium
                                                  │
                                                  ├─ agents/*.py   (COPY of Layer A appliers)
                                                  ├─ llm_router    (Ollama→Groq→Gemini)
                                                  └─ resume pipeline (jd_analyser→tailor→pdf→store)
```

**Run pipeline (the heart):** `routers/agents.py` → enqueue `AgentRun` → Celery `run_phase_task`
→ `_run_phase_logic` (workers/agent_tasks.py). That function:
1. Builds a `CONFIG` dict from the user's DB profile (`_build_config`).
2. **Monkey-patches** `agents/config.py`'s module-global `CONFIG`, after `sys.modules.pop(...)`
   flushing the cached applier modules so they re-import against the new config.
3. **Replaces `sys.stdout`** process-wide with an `AgentStdout` that scrapes printed lines
   ("✅ Applied", "⏭ Skipping", "❌ …") into WebSocket events + DB `AgentLog` rows.
4. Runs everything **inside one process-global `_config_lock`**.

**Inputs→Transform→Outputs per component:**
- *agent_supervisor*: (boot) → recover stuck runs, spawn worker if Redis up & none listening,
  start 60s watchdog → self-healing run state.
- *llm_router.generate(role)*: prompt → provider chain → text|None (never raises).
- *rate_limits.RateLimiter*: (user,platform) events → can_apply()/caps. **In-process singleton.**

---

## 2. Failure-discovery summary (Phase 2) → see §3 for ranked detail

Aggressively searched config, auth, crypto, the run pipeline, and rate limiting. Problems assumed
present until disproven. 12 issues found (3 critical, 4 high, 5 medium). The appliers, resume
pipeline, and frontend are not yet deep-read — expect more in pass 2–3.

---

## 3. Issues Found + Root-Cause Analysis (Phases 2–3)

### 🔴 CRITICAL

#### C1 — Real user database committed to a public repo
- **Evidence:** `git ls-files` tracks `jobagent.db` (270 KB). It contains **6 real users**
  (`users`, `user_profiles`, `payments`, `applications`, `agent_logs`, …). `.gitignore` *does* list
  `jobagent.db`/`*.db`, but the file was committed **before** the ignore rule, so git still tracks it.
- **Impact:** bcrypt hashes, Fernet-encrypted platform credentials + LinkedIn session cookies, emails,
  payment rows — all public. Encryption only helps until `FERNET_KEY` leaks; and `SECRET_KEY` is
  *derived from* `FERNET_KEY` (config.py:42-50), so one leak compromises both auth and credentials.
- **Issue → Immediate cause → Root cause:** leaked PII → file tracked despite .gitignore →
  `.gitignore` added after first commit; nobody ran `git rm --cached` → **no pre-commit secret/DB
  hygiene gate; binary DB used as the dev datastore inside the repo tree.**
- **Fix (pass 2):** `git rm --cached jobagent.db backend.db`, rotate `FERNET_KEY` + `SECRET_KEY`,
  force-invalidate all stored platform credentials/cookies, scrub history (BFG/filter-repo),
  notify the 6 users. Move dev DB outside the repo.

#### C2 — Whole platform serializes behind one global lock + global stdout
- **Evidence:** `agent_tasks.py:844` runs the entire phase inside `with _config_lock:` while
  `sys.stdout` is swapped process-wide (`:761`) and `agents.config.CONFIG` is mutated in place.
- **Impact:** regardless of Celery `--concurrency`, **only one user's run can execute at a time**
  across the entire backend. Two paying users = one waits behind the other indefinitely (a run can
  last many minutes). Throughput ceiling = 1. The architecture is fundamentally single-tenant code
  (module-global CONFIG + module-global stdout) retrofitted to multi-tenant via a lock.
- **Root cause:** appliers read `from config import CONFIG` at import time → shared mutable global →
  the only safe way to multiplex it is exclusion. **State lives in module globals, not per-run context.**
- **Fix:** the durable answer is to thread a per-run `config` object through the appliers (no globals);
  short-term, run each phase as its own subprocess (true isolation, no shared stdout/CONFIG).

#### C3 — Daily safety caps are not actually enforced
- **Evidence:** `rate_limits.default_limiter` is a **module-level in-memory singleton** (rate_limits.py:104).
  The Celery worker is a *separate process* (and may be respawned by the supervisor); `_check_quota`
  in the DB uses `date.today()` (local) while the limiter uses `datetime.utcnow()` + a sliding 24h window.
  PLAN.md §6 calls the daily cap "non-negotiable."
- **Impact:** caps reset on every worker (re)start and aren't shared across processes/workers → the
  LinkedIn-50/day account-safety rail can be silently exceeded → user accounts get flagged/banned.
  This is the system's core promise (don't get the user banned) failing quietly.
- **Root cause:** safety state kept in process memory; the module's own docstring admits "swap for Redis
  for multi-worker" but it was shipped in-memory.
- **Fix:** back the limiter with Redis (or the `usage_quotas` table) keyed by (user,platform,day).

### 🟠 HIGH

#### H1 — LinkedIn rate limiter never resets its failure counter
- **Evidence:** `grep register_success agents/linkedin_applier.py` → **0**. The applier calls
  `can_apply`, `register_apply` (twice), `register_failure`, but never `register_success`.
- **Impact:** `_failures` only ever increments. After 3 *cumulative* (not consecutive) failed applies
  in the worker's lifetime, LinkedIn is paused "until next success" — which can never arrive → LinkedIn
  applies silently stop until the worker restarts. Breaks the "consecutive" semantics §rate_limits.
- **Root cause:** wiring added per-applier by hand (commit d899ecb); the success-reset call was omitted
  for LinkedIn only (internshala/wellfound have it).

#### H2 — `decrypt()` masks failures by returning ciphertext as plaintext
- **Evidence:** crypto_service.py:27-28 `except Exception: return ciphertext`.
- **Impact:** intended as a legacy-plaintext fallback, but it also swallows *genuine* decryption
  failures (wrong/rotated key, corruption). A corrupted encrypted LinkedIn password is then typed
  into the login form as the literal base64 ciphertext → guaranteed failed login with no clear error;
  and it defeats key-rotation detection. Security + correctness.
- **Fix:** distinguish "looks like Fernet token" (starts `gAAAAA`) → on failure raise/log; only treat
  non-token values as legacy plaintext.

#### H3 — CORS trusts every `*.vercel.app` origin *with credentials*
- **Evidence:** main.py:120 `allow_origin_regex = https://.*\.vercel\.app|https://.*\.nutriblend\.store`
  + `allow_credentials=True`.
- **Impact:** **anyone** can deploy a malicious site to `*.vercel.app` and it becomes a
  credentialed trusted origin → CSRF / authenticated-request forgery against logged-in users.
  `.*` is also overly greedy. (JWT-in-header mitigates classic CSRF *if* tokens aren't in cookies —
  needs confirming in pass 3, but the wildcard is still wrong.)
- **Fix:** pin preview origins to the project's own Vercel scope, or validate a deploy-hash prefix;
  never combine wildcard origins with credentials.

#### H4 — Boot recovery can fight a live detached worker (status flapping)
- **Evidence:** `recover_stuck_runs()` marks **all** queued/running runs `failed` at startup
  (agent_supervisor.py:104), but `ensure_worker_running()` spawns the worker with
  `start_new_session=True` so it **survives a uvicorn --reload**.
- **Impact:** in dev/reload (and any web-process restart while a run is genuinely executing in the
  surviving worker) the run is marked `failed`, then the worker later flips it to `completed` →
  inconsistent status, misleading metrics, possible double-quota effects.
- **Root cause:** recovery assumes "web restart ⇒ all workers dead," which the detached-worker design
  violates.

### 🟡 MEDIUM

- **M1 — JWT has no token-type / revocation.** auth.py: access & refresh tokens are structurally
  identical (`{sub,exp}`); `/refresh` accepts *any* unexpired signed token (including an access token).
  No `jti`, no rotation, no blocklist. Add a `type` claim and reject mismatches.
- **M2 — Quota checked once per phase, not per apply.** `_check_quota` gates at phase start only; a
  single phase can submit well past the cap before `_increment_quota` runs at the end. Key name
  `applies_per_48hr` contradicts the "daily" framing elsewhere.
- **M3 — Self-learning grows `agent_custom_instructions` unbounded.** `_learn_from_run_logs` appends
  LLM-generated rules to the profile every run with only exact-string dedup; never pruned/capped →
  prompt bloat + cost creep, and LLM output is fed back into future prompts.
- **M4 — `check_schedules` cron parsing is naive (hour-only).** Comment admits it; compares
  `started_at >= date.today()` (datetime vs date) and only matches `parts[1]` → can mis-fire / miss.
- **M5 — In-thread fallback (Redis down) corrupts the web process.** Per PLAN, when no worker exists
  the phase runs in a background thread *inside uvicorn*, which means it swaps the web process's
  `sys.stdout` and holds the global lock → can mangle FastAPI's own logging and stall requests.
  (Needs confirmation in agents.py — pass 2.)

---

## 4. Ranked Hypotheses (Phase 5)

Ranked by (Impact × Confidence ÷ Complexity), competing explanations noted.

| # | Hypothesis | Conf | Impact | Cmplx | Risk |
|---|---|---|---|---|---|
| 1 | Committed DB has leaked real user PII/creds (C1) | ✅ proven | Critical | Low | — |
| 2 | Platform can only run 1 job at a time (C2) | High | Critical | High | refactor risk |
| 3 | Daily caps don't hold across worker restarts → bans (C3) | High | Critical | Med | — |
| 4 | LinkedIn stops applying after 3 lifetime failures (H1) | ✅ proven | High | Low | — |
| 5 | Corrupt/rotated creds typed verbatim into logins (H2) | High | High | Low | — |
| 6 | Malicious *.vercel.app origin can forge requests (H3) | Med | High | Low | needs cookie check |
| 7 | Run status flaps on web restart (H4) | Med | Med | Med | — |
| 8 | Resume tailor may emit hallucinated bullets despite guard | Unknown | High | — | **verify pass 2** |
| 9 | Stale agent modules survive `sys.modules.pop` (missed names) | Low | Med | Low | — |
| 10 | Quota bypass within a single long phase (M2) | Med | Med | Low | — |
| 11 | Self-learning prompt bloat raises cost per run (M3) | Med | Low | Low | — |
| 12 | In-thread fallback degrades the whole API (M5) | Med | High | Med | **verify pass 2** |

Competing explanation for "applies = 0" symptom (PLAN §6): could be LinkedIn login (cookies) OR
H1 (failure-counter lock) OR C3 (cap reached) OR C2 (run never gets the lock). Must instrument to
disambiguate — this is why §0's observability gap is the meta-problem.

---

## 5. Multi-persona review of the findings (Phase 4)

- **PM:** C1/C3 attack the product's core promise ("apply at scale without getting banned"). Fix first.
- **Senior Eng:** C2 is the real architectural debt — module globals + lock. Everything else is patchable.
- **QA:** no measured metrics anywhere (§0) → we can't prove any fix works. Add telemetry before tuning.
- **Security:** C1 + H2 + H3 + M1 are a coherent credential-exposure cluster; treat as one workstream.
- **Cost:** M3 (prompt bloat) + the Gemini self-learning call every run are slow cost leaks.
- **End user:** H1/H4 produce "it says failed/it stopped and I don't know why" — the worst UX.

---

## 6. Plan for next passes (Phases 6–12)

- **Pass 2:** ✅ DONE — see §6b.
- **Pass 3:** ✅ DONE — see §6c.

---

## 6b. Pass 2 results (2026-06-09) — appliers + resume pipeline + tests

**Regression baseline established:** `pytest tests/` → **56 passed, 0 failed** (1 Pydantic-v1 deprecation
warning in config.py:30). The career-pipeline units (jd_analyser, resume_tailor, resume_pdf, resolver,
store, rate_limits, linkedin_cookies, response_rates) all pass. This is the green baseline any future
change must not break.

### Verified GOOD (the strongest part of the system)
- **Hallucination guard works (H#8 downgraded).** `resume_tailor.tailor` (resume_tailor.py:262-295) drops
  any bullet whose `evidence_in_profile` is empty or not in the profile's real bullet-id set
  (`valid_ids`, :274). Header fields (name/email/phone) are always taken from the profile, never the LLM
  (:304-308). On LLM failure/garbage/empty-after-guard it falls back to an untailored resume built from
  the profile where every bullet is its own evidence (`_fallback_untailored`) — cannot ship empty, cannot
  hallucinate. PLAN Phase B acceptance is met at the unit level.
- **jd_analyser** also filters `must_haves`/`nice_to_haves` against the JD text (jd_analyser.py:87-102) and
  never raises. (Minor: `keywords` are NOT filtered — trusted from the LLM. Cosmetic only; keywords don't
  assert experience.)
- **resume_resolver** never raises; tailored-PDF on success, static PDF on any failure (resolver.py:55-57).
- **LinkedIn cookie login** is well-built (linkedin_applier.py:108-188): requires `li_at`, strips toxic
  cookie fields, verifies post-injection landing URL, and auto-refreshes rotated cookies back to the DB.

### New issues found in pass 2

#### 🟠 H5 — IDOR: run logs are not scoped to the requesting user
- **Evidence:** `GET /agents/runs/{run_id}/logs` (agents.py:354-369) and
  `POST /agents/runs/{run_id}/analyze` (:371-431) query `AgentLog` **by `run_id` only** — no `user_id`
  filter. Compare `run_status` (:251-266) and `pause_run`, which correctly scope by `user_id`.
- **Impact:** any authenticated user who knows/guesses a `run_id` (UUID) can read **another user's** run
  logs — which contain scraped page text, error detail, and login-challenge messages. Broken
  object-level authorization (OWASP A01). UUIDv4 makes enumeration hard but does not make it authorized.
- **Fix:** join `AgentRun` and filter `AgentRun.user_id == user.id` before returning logs (one-line guard).

#### 🟡 M6 — `/analyze` is a wallet-DoS on the platform's own Gemini key
- **Evidence:** `analyze_run_logs` (agents.py:392-415) calls Gemini using `settings.system_gemini_key`
  (the **operator's** key, not the user's), is **not plan-gated** and **not rate-limited**, and is callable
  per run on demand. It also duplicates `_learn_from_run_logs` (M3).
- **Impact:** any user can drive operator-paid LLM spend by repeatedly hitting /analyze; combined with H5
  they can even analyze runs that aren't theirs. Cost leak + abuse vector.
- **Fix:** gate behind plan, rate-limit, and/or charge to the user's own key; dedupe with the worker's
  self-learning path.

#### 🟡 M7 — Phase E (JD-tailored PDF) is only wired into 2 of ~6 appliers
- **Evidence:** `grep resolve_resume_path agents/` → present only in `linkedin_applier.py` and
  `wellfound_applier.py`. Absent from `internshala_applier`, `web_search_applier`, `google_form_filler`,
  `other_platforms`.
- **Impact:** PLAN's headline promise ("every application ships a JD-tailored PDF") holds **only** for
  LinkedIn + Wellfound. Internshala / web-search / form-fill submit the **static** resume. The product's
  central value prop is ~⅓ delivered. (Functionally safe — static upload still works — but the claimed
  differentiation is missing where most volume likely happens.)
- **Fix:** call `resolve_resume_path(config, jd_text=...)` at each applier's file-upload step (PLAN Phase E).

#### 🟠 M5 — CONFIRMED (was "needs confirmation")
- `routers/agents.py:159-172`: when Redis/worker is down, phases run in a **daemon thread inside the
  uvicorn web process** via `_run_phase_logic`, which swaps process-global `sys.stdout` and holds the
  global `_config_lock`. So the fallback path degrades the API process itself (stdout capture + lock
  contention), and confirms C2 applies to the web process too, not just the worker. Promote to **HIGH**.
- **Then:** experiment design per fix (objective/variables/rollback), regression run, metrics comparison,
  and a per-fix APPROVE/REJECT/NEEDS-MORE-TESTING decision.

### Deployment decision so far: **REJECT any deploy until C1 + H5 are remediated.**
C1 (leaked user DB) is an active data-exposure incident and outranks all feature work. Pass 2 added
**H5 (IDOR on run logs)** to the must-fix-before-deploy set. Tally after pass 2: **15 issues**
(3 critical, 5 high incl. promoted M5/H5, 7 medium). Test baseline is green (56 passed) so fixes can be
verified against it.

---

## 6c. Pass 3 results (2026-06-09) — frontend, stress tests, observability

### Frontend auth model (settles H3)
- **JWT lives in `localStorage`** (zustand-persist key `auth-store`) and is attached as an explicit
  `Authorization: Bearer` header by an axios interceptor (api.ts:58-86). **Not a cookie.**
- **Production talks same-origin:** the real frontend uses a Next.js rewrite proxy (`/api/*` →
  `BACKEND_URL` server-side, api.ts:13-47), so the browser only ever hits `nutriblend.store` — **CORS is
  not even exercised by legitimate traffic.**

- **→ H3 DOWNGRADED (High → Low/informational).** Because auth is header+localStorage (not cookie-borne),
  the wildcard `*.vercel.app` + `allow_credentials=True` does **not** enable session theft or CSRF: a
  malicious cross-origin page can neither read the victim's localStorage nor auto-attach the Bearer token.
  The wildcard is still bad hygiene (would bite the moment any endpoint trusts a cookie) and should be
  tightened, but it is **not a practical exploit** in the current design. Honest correction to pass 1.

### New issues found in pass 3

#### 🟡 M8 — JWT (incl. 30-day refresh) in localStorage → XSS-exfiltration risk
- Storing both access and the long-lived refresh token in localStorage means any XSS (or a single
  compromised npm dependency) can exfiltrate them; the refresh token grants 30-day account access and
  there is no server-side revocation (ties to M1). Tradeoff is acceptable for an MVP but should be a
  documented, eyes-open decision; consider httpOnly-cookie refresh + short-lived access, or at least
  refresh-token rotation + a revocation list.

#### 🟡 M9 — WebSocket auth token passed in the URL query string
- `/ws/{user_id}?token=<JWT>` (main.py:150). Tokens in URLs leak into server/proxy access logs, the
  Railway request log, and browser history. Prefer a post-connect auth message, or a short-lived
  single-use WS ticket. (WS handler does validate the token correctly — the issue is the transport, not
  the check.)

#### 🟢 N1 — Zombie Chrome processes accumulate (ops/cost)
- Appliers run with Selenium `detach=True` and `safe_quit()` **never calls `driver.quit()`**
  (main.py:112-118 — "leave tabs open for manual review", a Layer-A UX choice). In the server (Layer B)
  this means every run leaves a Chrome process alive → unbounded memory growth on the Railway box until
  OOM. Server-side runs must `quit()` even though the local CLI intentionally doesn't.

### Stress-test reasoning (Phase 8) — verdict per scenario
| Scenario | Behaviour | Verdict |
|---|---|---|
| API down / Railway cold start | 60s axios timeout + warm-up ping + 401→refresh→/login | ✅ handled |
| Chrome crash mid-run | applier try/except → phase returns; 5-min watchdog fails truly-hung runs | ✅ handled (but N1 leaks procs) |
| Empty / ambiguous JD | jd_analyser truncates to 8k, never raises, returns safe-empty signature | ✅ handled |
| **Adversarial JD (prompt injection)** | JD is interpolated into the LLM prompt, BUT output is JSON-parsed, `must_haves` filtered to appear in JD, and resume_tailor drops any bullet lacking real profile evidence | ✅ **contained by the guards** — injected "experience" cannot reach the PDF |
| SQLite JSON column returns str/list/None | `_ensure_dict` coerces everywhere it's read | ✅ handled |
| Concurrent runs (same or diff user) | global `_config_lock` serializes → no corruption, **but zero parallelism** | ⚠️ correctness-safe via C2, which is itself the scalability defect |

Net: the system is **robust against bad/adversarial input and crashes** (the "bulletproof" work paid off),
but **not robust against scale** (C2) or **operational drift** (N1 zombie Chrome, C3 cap reset).

### Observability proposal (Phase 10 — the meta-gap from §0)
The DB already has the bones (`agent_runs.applied/skipped/error_count`, `job_outcomes`, `ai_requests`,
`agent_logs`). What's missing is aggregation + LLM-usage capture. Minimal, high-leverage plan:
1. **Success metrics** — `GET /admin/metrics`: per-platform `success_rate = applied/(applied+errors)`,
   applies/day, login-challenge rate (count AgentLog.event_type='login_challenge'). All derivable today.
2. **Latency** — derive from `started_at`/`completed_at` already on AgentRun; surface p50/p95 per phase.
3. **Cost** — `llm_router.generate` currently returns text only. Add usage capture (provider, model,
   prompt/output tokens) → write to the existing `ai_requests` table. Without this, "token usage / cost"
   in the brief is unanswerable.
4. **Funnel** — jobs_found → match_passed → applied → callback (join `job_outcomes`). This is the only
   metric that actually measures the product's value (resume_relevance × volume from PLAN §0).
Until at least #1 and #3 exist, every tuning decision is blind.

---

## 7. FINAL CONSOLIDATED REPORT (audit complete — 3 passes)

**Scope covered:** docs, backend run pipeline, supervisor/worker, LLM router, security (crypto/auth/CORS/
rate-limits), resume pipeline (jd_analyser/tailor/pdf/resolver/store), appliers (linkedin deep, others via
grep+targeted), frontend auth/api/ws, test suite (56 green), stress reasoning, observability.

**Tally: 17 findings** — 3 critical, 4 high, 8 medium, 2 low/note (after H3 downgrade, +M8/M9/N1).

**Prioritized remediation plan (do in this order):**

| Rank | ID | Fix | Effort | Gate |
|---|---|---|---|---|
| 1 | **C1** | `git rm --cached jobagent.db backend.db`; rotate FERNET_KEY+SECRET_KEY; invalidate stored creds/cookies; scrub history; notify 6 users | S (urgent) | **blocks deploy** |
| 2 | **H5** | Scope `/agents/runs/{id}/logs` & `/analyze` by `user_id` (one-line join) | XS | **blocks deploy** |
| 3 | **H1** | Add `register_success` to linkedin_applier on successful apply | XS | safety |
| 4 | **C3** | Back RateLimiter with Redis/`usage_quotas` keyed (user,platform,day) | M | safety promise |
| 5 | **H2** | `decrypt()` — only treat non-Fernet-token values as legacy plaintext; log real failures | S | security |
| 6 | **M6** | Plan-gate + rate-limit `/analyze`; dedupe with worker self-learning | S | cost |
| 7 | **N1** | Server-side runs must `driver.quit()` in a finally | S | ops/cost |
| 8 | **M7** | Wire `resolve_resume_path` into internshala/web_search/form_fill appliers | M | core value prop |
| 9 | **C2/M5** | The big one: thread per-run config (no module globals) or run each phase as a subprocess → unlocks concurrency + removes global stdout/lock from the web process | L | scale |
| 10 | M1/M2/M3/M4/M8/M9/H4 | token-type claim; per-apply quota; cap self-learning growth; real cron (croniter); WS ticket; recovery-vs-worker reconciliation | M total | hardening |

**Deployment decision (Phase 11): NEEDS WORK — REJECT until C1 + H5 are fixed** (ranks 1–2). They are an
XS+S pair and unblock a safe deploy. Ranks 3–8 are the next sprint; rank 9 (C2) is the architectural
investment that makes the product multi-tenant for real.

---

## 7c. Remediation log (branch `audit-remediation`, 2026-06-09)

Fixes applied and verified against the 56-test baseline (still green after every batch):

| ID | Status | What shipped |
|---|---|---|
| C1 | ✅ code done; ⚠️ operator must rotate keys + scrub history | `git rm --cached jobagent.db`; `docs/SECURITY_INCIDENT_C1.md` runbook |
| H5 | ✅ done | `_owned_run_or_404` guards `/runs/{id}/logs` & `/analyze` |
| H1 | ✅ done | linkedin applier calls `register_success` on apply |
| H2 | ✅ done | `decrypt()` returns "" on real Fernet failure (gAAAAA check), not ciphertext |
| C3 | ✅ done | `RedisRateLimiter` + `_LazyLimiter`; caps survive restart, shared across procs |
| M6 | ✅ done | `/analyze` gated to Pro + per-user daily cap (analyze:20) |
| N1 | ✅ done | server runs (`_server_mode`) quit Chrome instead of detaching |
| M7 | ✅ plumbing done | resolver wired into smart_form_filler + google_form_filler chokepoints (covers internshala/web_search/form_fill). Follow-up: appliers must set `_current_jd` to actually tailor on those platforms |
| M1 | ✅ done | JWT `type` claim; refresh/access not interchangeable (legacy-tolerant) |
| M3 | ✅ done | self-learning instructions capped at 25 deduped rules |
| H4 | ✅ done | boot recovery only fails `queued` runs; watchdog handles `running` (no worker race) |
| M4 | ✅ done | `croniter`-based schedule matching w/ hour-check fallback; dep added |
| M2 | ✅ mitigated | per-apply enforcement now comes from the persistent limiter (C3); appliers call `can_apply` before each apply. DB `_check_quota` remains the per-phase plan quota |
| **C2/M5** | ⏳ **planned, not implemented** | Design in `docs/C2_CONCURRENCY_PLAN.md`. Deliberately not blind-rewritten — unverifiable without a live worker/Chrome/Redis stack; would violate Phase 9 (no unverified regressions) |
| M8 | 📝 documented | localStorage JWT/refresh = XSS-exfil tradeoff; recommend httpOnly-cookie refresh + rotation (future) |
| M9 | 📝 documented | WS token-in-URL → move to a post-connect auth message / single-use ticket (future, frontend+backend) |

**Deploy gate now satisfied:** C1 (code) + H5 are fixed → a safe deploy is unblocked
**once the operator completes the C1 key-rotation/history-scrub runbook.** C2 remains the
next major investment (needs a live stack to implement + verify).

---

## 7b. Learnings (Phase 12, running)
- The "bulletproof layer" (PLAN §5) genuinely improved *liveness* (stuck-run recovery, worker respawn)
  but introduced *safety/consistency* regressions (H4 status flap; the global lock that caps throughput).
- Robustness-by-global-state (module CONFIG, module stdout, in-memory limiter) is the recurring root
  cause behind C2/C3/H1/M5. Future work should push state into per-run context + a shared store.
- The system optimizes things it cannot measure. Observability is prerequisite, not polish.
