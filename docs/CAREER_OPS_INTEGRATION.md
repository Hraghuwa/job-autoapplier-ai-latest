# Career-Ops Integration

Ported the [career-ops](https://github.com/santifer/career-ops) filter/tailoring layer into JobAgent. JobAgent handles auto-apply; career-ops decides **what's worth applying to** and tailors materials per JD.

## What shipped

### Backend — `backend/routers/career_ops.py` mounted at `/career-ops/*`

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/career-ops/evaluate` | A–G evaluation (role / CV match / level / comp / personalization / interview / legitimacy) |
| POST | `/career-ops/tailor-cv` | Tailored summary, keywords, bullet rewrites, ATS tips |
| POST | `/career-ops/scan` | LLM-suggested target companies + portal URLs |
| GET/POST/DELETE | `/career-ops/story-bank[/{id}]` | STAR+R story bank |
| POST | `/career-ops/negotiation` | Counter / geo pushback / competing-offer scripts |
| GET | `/career-ops/health` | Liveness + AI-configured check |

Auth: all routes use `get_current_user` (JWT Bearer).
CV context: `UserProfile.extracted_data` (populated on resume upload).
AI: Gemini 1.5 Flash via `GEMINI_API_KEY`.
Storage: in-memory dicts per user (v1 slice). Migration path documented in skill file.

### Frontend — `frontend/app/(app)/career-ops/page.tsx`

Tabbed client page: **Evaluate · Tailor · Scan · Story Bank · Negotiate**. Added to main nav (Target icon). Uses existing `@/lib/api` axios client with auto JWT injection.

### Skill — `~/.claude/skills/career-ops/SKILL.md`

Registers a reusable Claude skill so future sessions know the endpoints, extension points, and how to add new evaluation dimensions without breaking the frontend block renderer.

## Public landing page

`frontend/app/page.tsx` is already a public landing page — there is **no middleware** gating it at the code level.

If users are redirected to a Vercel login before seeing the page, that is **Vercel Deployment Protection** (a project-level setting, not a code issue). To fix:

1. Vercel Dashboard → your project → **Settings**
2. **Deployment Protection**
3. Set to **"Only Preview Deployments"** (or **Disabled**) for production
4. Redeploy

No code change can bypass this — it runs at Vercel's edge before your Next.js app renders.

## Verification

- Backend: `python3 -m py_compile backend/routers/career_ops.py` → OK
- Frontend: `tsc --noEmit` → exit 0, zero errors

## Remaining work (follow-ups)

1. **Persist story bank + evaluations to DB** — currently in-memory. Add `CareerOpsEvaluation` + `InterviewStory` models, Alembic migration.
2. **Real portal scanner** — port `scan.mjs` (Greenhouse/Ashby/Lever JSON APIs, zero-token) into `backend/services/portal_scanner.py`. The current `/scan` is an LLM suggestion shim.
3. **ATS PDF generation** — port `generate-pdf.mjs` + `templates/cv-template.html` into a `POST /career-ops/generate-pdf` route using Playwright (already in agents stack).
4. **Live application assistant** — port `modes/apply.md` flow.
5. **Follow-up cadence tracker** — port `followup-cadence.mjs`.
