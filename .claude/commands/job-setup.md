---
description: First-time JobAgent setup — widen titles from your resume, nearby locations, targets, CV, dry-run mission
argument-hint: <roles, location, level — e.g. "business analyst intern, Bangalore or remote, entry">
---
Set up my JobAgent job search using the `jobagent` MCP tools. My starting target: **$ARGUMENTS**
(If that's empty, work it out from my resume in step 2 and confirm it with me.)

Work through these steps in order. Stop at each ⏸ and wait for my answer.

1. **Health check** — call `jobagent_readiness_check` (it lists every blocker with its fix) and `jobagent_get_profile`. If a tool errors with "Can't reach JobAgent", tell me to start the backend (`.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 3002`) and stop. If it says "Not logged in", tell me to run `.venv/bin/python -m backend.scripts.mcp_login <my email>` and stop. If `has_resume` is false, tell me to upload my resume on the Credentials page and stop.
   If `has_resume` is true but `resume` is empty, the upload wasn't parsed (usually no working Gemini/Groq key at the time). Read the PDF at `resume_file` yourself if you can (it's a path relative to the JobAgent repo, e.g. `/Users/hragh/Downloads/res/uploads/...`) and use that text for step 2; otherwise ask me to add a working AI key in Settings and re-upload the resume on Credentials. Don't guess my experience.

2. **Widen the targets from my resume** — using `jobagent_get_profile` (resume skills, experience, education, summary) plus my starting target:
   - **Job titles:** my main title, plus 6–10 *related* titles I'm genuinely qualified for — same skills under other names (e.g. Business Analyst → Data Analyst, MIS Analyst, Operations Analyst, Reporting Analyst, Product Analyst), adjacent roles my experience supports, and common Indian job-board variants. Every title must be backed by something on my resume; no stretch roles I'd fail the screen for. Keep them short and searchable (no seniority words — the level is set separately).
   - **Locations ("nearby"):** my city, the nearby cities/metro areas I could reasonably work in or commute to (e.g. Bangalore → Bengaluru, Whitefield, Electronic City, Mysuru; Delhi → Noida, Gurugram, Ghaziabad, Faridabad), plus "Remote" and "India" if I'm open to them.
   - **Level** (`target_seniority`: intern / entry / associate / mid / senior) and **employment types** (Full-time, Internship, …) from my experience and starting target.
   - Show one table: title · why it fits (the resume evidence) · match strength (strong/good). Then the location list, level and types. Also show my current saved targets from `jobagent_get_profile` so I can see what changes.
   ⏸ Ask which titles and locations to keep (default: all strong + good ones). Then `jobagent_set_job_targets` with the **full** approved lists (it replaces what's saved). Confirm what's now saved.

3. **Find companies** — `jobagent_scan_portals` with my top 3 titles + main location. It returns a brief: use your own web search to find real companies hiring for these titles and verify each careers / Greenhouse / Lever URL before listing it. Show a numbered table: company · why · portal type (Greenhouse / Lever / other). ⏸ Ask which numbers to keep.

4. **Save targets** — `jobagent_save_mission_targets` for my picks. Report which boards were verified and how many open roles, and which portal links were skipped as unverifiable.

5. **Answer bank** — `jobagent_answer_bank`. For every missing standard question and every question missions couldn't answer, propose an answer from my resume (experience years, qualification, graduation year, LinkedIn, location…) and ASK me for the ones only I know (current/expected CTC, notice period, joining date, relocation, bond, shifts). Never guess those. ⏸ Show the full list, then `jobagent_save_answers` with what I confirm — missions will fill these on every form without AI.

6. **Tailor the base CV** — pick one real job description from a saved company that matches my main title (ask me to paste one if you can't get one), then `jobagent_tailor_cv` — it returns a brief; write the suggestions yourself in the JSON shape it describes. Show the summary, each keyword, and each rewrite next to its original. ⏸ Ask what to keep; for keywords, only ones I confirm I actually have. Then `jobagent_apply_cv_tailoring` with exactly what I approved.

7. **Dry run across all titles** — `jobagent_launch_mission` with `["web_search", "linkedin"]` and `dry_run: true`. Missions search every saved title in every saved location automatically. Poll `jobagent_mission_status` every minute or so until it finishes, then summarise `jobagent_mission_logs`: jobs found per title, what it skipped and why (wrong level, location, low fit), any errors. If a title found nothing or only poor fits, suggest dropping or renaming it.

8. ⏸ Ask whether to launch for real. Only on a clear yes, `jobagent_launch_mission` without dry_run — it will apply to matching jobs for all saved titles, leaving any form that needs my input open as "prepared" for me to submit.

End with a 4-line summary: titles + locations being searched, companies targeted, CV changes applied, mission state.
