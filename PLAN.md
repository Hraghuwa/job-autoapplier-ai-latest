# PLAN — JD → tailored-PDF resume → auto-apply

> Goal: every application the agent submits ships with a **PDF resume tailored
> to that specific JD**, generated automatically, no manual step. Higher
> response rate per submission, more submissions per day, real signal on
> what's working.
>
> **Honest framing:** this raises offer probability significantly — it does
> not guarantee one. Anyone who promises "100% job offer" is selling, not
> engineering. Below is engineering.

---

## 0. Reality check — what determines offers (so we optimise the right thing)

```
Offer = f(
   #applications × resume_relevance × profile_fit × outreach_quality × luck
)
```

The agent moves the dials we can move:
- **#applications/day**: today ~20–50 manual → 200–500 automated.
- **resume_relevance**: static PDF → JD-tailored PDF per application.
- **profile_fit**: not magic — we surface only jobs above match-score floor.
- **outreach_quality**: cover note + LinkedIn opener auto-personalised.
- **luck**: not a dial. Volume × relevance is how you buy more dice rolls.

What we explicitly will NOT do:
- Fabricate experience.
- Pretend to be a different person on LinkedIn.
- Bypass captchas with stolen sessions.

---

## 1. System shape

```
            ┌──────────────────────┐
            │  Job discovery       │  (existing: web_search_applier,
            │  → job_url, jd_text  │   wellfound_applier, etc.)
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  JD analyser         │  llm_router(role=writer):
            │  → JD signature      │   keywords[], must_haves[], nice_to_haves[],
            │                      │   seniority, archetype, red_flags[]
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  Match gate          │  score_match() — skip if < floor (default 55)
            └──────────┬───────────┘
                       │ pass
                       ▼
            ┌──────────────────────┐
            │  Resume tailor       │  Surgical rewrite from user_profile JSON
            │  (no hallucination)  │   → tailored_resume JSON (sections + bullets)
            │                      │   Quality gate: every bullet must trace to
            │                      │   evidence_in_profile or be dropped.
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  PDF renderer        │  ReportLab / WeasyPrint — deterministic,
            │  (ATS-safe template) │   1 column, real text (not images),
            │                      │   selectable, < 200 KB
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  Resume cache        │  hash(jd_signature + profile_version)
            │                      │   → /uploads/tailored/{hash}.pdf
            │                      │   Re-used across reruns of same JD.
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  Application worker  │  uploads tailored PDF instead of
            │  (smart_form_filler) │   profile.resume_url, plus cover_note
            │                      │   tailored by llm_router(role=writer).
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  Outcome tracker     │  application_id ← tailored_resume_id
            │                      │   → per-resume response rate, A/B data
            └──────────────────────┘
```

---

## 2. Data additions (sqlite + pg)

```sql
-- One row per tailored-resume artifact. Many applications can point to one.
CREATE TABLE tailored_resumes (
  id            CHAR(32) PRIMARY KEY,
  user_id       CHAR(32) NOT NULL,
  jd_hash       TEXT NOT NULL,          -- hash of JD signature
  jd_signature  JSON,                   -- {keywords, must_haves, archetype, …}
  resume_json   JSON,                   -- structured tailored content
  pdf_path      TEXT NOT NULL,          -- /uploads/tailored/{hash}.pdf
  pdf_bytes_sha TEXT,                   -- integrity check
  model_used    TEXT,                   -- 'qwen2.5:14b' | 'gemini-2.0-flash'
  profile_ver   INTEGER,                -- bump when user updates profile
  jd_coverage   REAL,                   -- 0..1, fraction of must_haves hit
  hallucination_flags JSON,             -- audit trail
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, jd_hash, profile_ver)
);

ALTER TABLE applications
  ADD COLUMN tailored_resume_id CHAR(32);

ALTER TABLE applications
  ADD COLUMN cover_note_used TEXT;
```

---

## 3. Module breakdown (where each piece lives in the repo)

| Concern | New / changed file | Responsibility |
|---|---|---|
| JD analyser | `backend/services/jd_analyser.py` (new) | LLM-call → JD signature JSON, cached by `hash(jd_text)` |
| Resume tailor | `backend/services/resume_tailor.py` (new) | profile + JD signature → resume_json, with hallucination guard |
| PDF renderer | `backend/services/resume_pdf.py` (new) | resume_json → ATS-safe PDF via ReportLab |
| Resume cache | `backend/services/tailored_resume_store.py` (new) | get-or-build by (user_id, jd_hash, profile_ver) |
| Application flow | edits in `agents/*_applier.py` | swap static resume.pdf for tailored PDF before upload |
| Outcome data | `backend/routers/applications.py` (new endpoint) | per-resume response-rate report |
| UI | `frontend/app/(app)/automation/page.tsx` | show "tailored resume preview" before send + per-job response rates |

---

## 4. Phased delivery (each phase is independently shippable)

### Phase A — JD analyser + match gate (1 day)
- [ ] `jd_analyser.analyse(jd_text)` → returns signature dict.
- [ ] `score_match` (already exists) gains a `must_haves_missing[]` field.
- [ ] Add CLI smoke test: `python -m backend.services.jd_analyser sample_jd.txt`.

**Acceptance:** running on 10 sample JDs returns valid JSON with no
hallucinated must-haves not in the text.

### Phase B — Resume tailor (2 days, the hard one)
- [ ] Define `profile_schema.json` — every claim in profile is structured
  (companies, roles, dates, bullet IDs).
- [ ] `resume_tailor.tailor(profile, jd_signature)` returns:
  ```json
  {
    "summary": "…",
    "keywords_added": ["python", "fastapi", "agentic"],
    "experience": [
      {
        "company": "Acme",
        "role": "Engineer",
        "bullets": [
          { "id": "b_acme_3", "text": "Rewritten bullet…",
            "evidence_in_profile": "b_acme_3_raw",
            "keywords_hit": ["python", "agentic"] }
        ]
      }
    ],
    "skills_ordered": ["…"]
  }
  ```
- [ ] **Hallucination guard:** reject any bullet whose `evidence_in_profile`
  is null or points to an ID that doesn't exist in the source profile.
  Drop those bullets, do not rewrite them.
- [ ] Cap rewrite *intensity*: only the top-K bullets per role can be
  reworded; the rest must be verbatim.
- [ ] Compute `jd_coverage = |must_haves ∩ keywords_in_resume| / |must_haves|`.

**Acceptance:** for a known JD + known profile, regenerate 20 times → 0
hallucinated bullets across all runs. `jd_coverage ≥ 0.7` on >80% of pairs.

### Phase C — PDF renderer (1 day)
- [ ] ReportLab template `templates/resume_ats.py` — single column, no images,
  Helvetica + selectable text, page margins 18mm, 10–11pt body.
- [ ] Embed structured metadata in PDF (`/Keywords`, `/Title`) so ATS parsers
  pick up keyword hits even from sloppy scrapers.
- [ ] Render-time invariants:
  - file size < 200KB
  - 1 page if profile fits, max 2
  - `pdftotext` round-trip preserves > 95% of bullet text

**Acceptance:** Greenhouse / Lever / Workday upload + auto-parse correctly
shows the tailored skills (visual sanity-check on 3 portals).

### Phase D — Cache + storage (½ day)
- [ ] Migration adds `tailored_resumes` table.
- [ ] `tailored_resume_store.get_or_build(user_id, jd_text)` orchestrates
  A → B → C, writes to disk + DB, returns row.
- [ ] Disk path: `uploads/tailored/{user_id}/{jd_hash}.pdf`.
- [ ] On profile update bump `profile_version` so caches re-build automatically.

### Phase E — Wire into appliers (1 day)
- [ ] In every `*_applier.py` upload step, swap `config["resume_path"]` for
  `tailored_resume_store.get_or_build(...).pdf_path` before the file input
  is sent.
- [ ] Persist `tailored_resume_id` + `cover_note_used` onto the `applications`
  row so we can A/B later.

**Acceptance:** end-to-end run on Internshala submits 3 applications, all 3
DB rows have a non-null `tailored_resume_id` pointing to a valid PDF.

### Phase F — Outcome tracker + UI (1 day)
- [ ] New endpoint `GET /applications/response-rates` groups by
  `tailored_resume_id` and `jd_signature.archetype`.
- [ ] UI shows: "tailored resume → applications sent → callbacks received →
  response rate".
- [ ] Patterns tab now also surfaces "best-performing keywords" — keywords
  whose presence in the tailored resume correlates with callbacks.

### Phase G — Quality + safety rails (½ day)
- [ ] Daily cap per platform (LinkedIn 50, Internshala 100, Wellfound 30) —
  prevent the account from getting flagged.
- [ ] Polite delay between applies (15s ± jitter).
- [ ] Skip-list: never re-apply to same `job_hash` within 90 days.
- [ ] Auto-pause the run if 3 consecutive applies fail (avoids the bot tripping
  a captcha and blasting it 50 more times).

---

## 5. The "bulletproof" layer (already shipped this session)

For the "make it always work" half of the ask — done:

| Failure mode | Before | After |
|---|---|---|
| Worker crashed / never started | Tasks queued forever, UI shows "queued" | `agent_supervisor.ensure_worker_running()` re-spawns at startup AND on every `/agents/healthcheck` poll |
| Run thread killed by uvicorn reload | Run sits "running" forever | `agent_supervisor.recover_stuck_runs()` at boot + watchdog every 60s |
| Chrome / Ollama / Redis down | Silent failure | `GET /agents/healthcheck` returns per-dependency truth, UI can show it |
| Redis up but no worker (the original bug) | Task disappears | `agents.py` detects no consumer → thread fallback |
| LLM provider down | Hard 503 | `llm_router` chain Ollama → Groq → Gemini, then graceful None |

---

## 6. Known limits (no magic)

- **LinkedIn login** ≠ password auth in 2026 — needs cookie injection
  (already half-built in `agents/linkedin_applier._try_cookie_login`).
  Plan: dedicated "Connect LinkedIn" flow that opens a Chrome window for
  the user to log in once, then we extract & encrypt the session cookies.
  Without this, Phase 1 will keep applying = 0.
- **Captchas** on Naukri / Workday — when one trips, we pause that platform
  for 24h. We do not solve captchas algorithmically (that is a TOS violation
  and also doesn't work).
- **Rate limits** — LinkedIn detects >50 applies/day from a fresh account.
  The daily cap (Phase G) is non-negotiable.
- **Quality of tailoring is bounded by profile quality.** If the user's
  source profile is one line ("software engineer"), no model can magic that
  into a hireable resume. The onboarding flow needs a "minimum viable
  profile" gate before runs are allowed.

---

## 7. Suggested execution order

1. Apply the bulletproof layer (DONE — verify by running a phase tonight).
2. Phase A + B (JD analyser + resume tailor) — biggest leverage, can ship
   without Phase C if we use a Markdown→PDF intermediate.
3. Phase C + D (real PDF + cache).
4. Phase E wires it in.
5. Phase F + G are observability + safety; ship in week 2.

Total: ~6 working days for one engineer. Half if you parallelise A/C/D.
