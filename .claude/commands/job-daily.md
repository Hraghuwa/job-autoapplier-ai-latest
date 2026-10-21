---
description: Set up or review daily auto-apply (LinkedIn, Wellfound, web search, ...) through the JobAgent MCP server
---
Use the `jobagent` MCP tools. $ARGUMENTS

1. `check_ready` — fix any hard errors with the user (resume, job titles). Note which platforms lack a saved login; those missions will be skipped.
2. `get_schedule` — if a daily schedule exists, show it (missions + time) and ask whether to keep, change or pause it.
3. Otherwise ask which missions to run daily (default: `linkedin`, `wellfound`, `web_search`), what time, and the user's UTC offset (e.g. `+05:30` for India). If they have never run a mission, offer a `launch_mission` dry run first.
4. After the user confirms (daily runs submit real applications), call `schedule_daily_missions`.
5. `progress_report` — summarise: total applied, this week, per platform, per status, response rate, and the last runs' applied/skipped/error counts. Flag runs with errors and offer `mission_logs` for them.
6. `followups_due` — list anything waiting on a follow-up and offer `draft_followup`.
