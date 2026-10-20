---
description: Weekly JobAgent review — what converts, skill gaps, target refresh
argument-hint: [hours per week for learning, default 6]
---
Run my weekly JobAgent review with the `jobagent` MCP tools.

1. **Funnel** — `list_applications` (limit 500). Show counts by status and the reply rate (viewed/shortlisted/interview/offer ÷ total). Name the companies or role types that got replies vs the ones that never do.
2. **Skill gaps** — `skill_gaps`, then `study_plan` with hours_per_week = $ARGUMENTS (6 if empty). Show the top 3 skills, each with resources, hours, and the proof project.
3. **Titles** — from the funnel, name the job titles that get replies and the ones that never do; using `get_profile`, suggest titles to add (related roles my resume supports) or drop. Apply only what I approve with `set_job_targets` (full list).
4. **Targets** — `list_mission_targets`. Suggest which to drop (no replies, 0 open roles) and run one `scan_portals` for my current target to suggest up to 5 new companies.
5. **CV check** — if replies are low (under ~5%), suggest one `tailor_cv` pass on a typical job description from the companies that did reply.

⏸ Ask me to approve: title changes, targets to remove (`remove_mission_target`), targets to add (`save_mission_targets`), and whether to run the CV pass. Apply only what I approve.
