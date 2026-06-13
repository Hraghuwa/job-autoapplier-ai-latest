# Database setup & migration (Railway → Neon/Supabase)

## Why login broke
The backend stores all users in Postgres, read from the `DATABASE_URL` env var.
When Railway's free plan expired, that Postgres was torn down — so every DB query
(including `/auth/login` and `/auth/register`) failed, which surfaced on the
frontend as a generic "login issue". **The code was never the problem** — a local
register→login→/auth/me round-trip passes against any working DB.

To see the DB state at a glance now: `GET /health` returns
`{"database": "ok" | "unreachable", ...}` (it still returns HTTP 200 so platform
healthchecks pass). `unreachable` = the DB, not the app, is down.

## The provider-agnostic design
`backend/database.py` reads `DATABASE_URL` and coerces it to the async driver
(`postgresql://` / `postgres://` → `postgresql+asyncpg://`). Switching providers
is **only** an env-var change — no code edits.

## Pick a new database (free, always-on)
| Provider | Notes | `DATABASE_URL` shape |
|---|---|---|
| **Neon** (recommended) | Free serverless Postgres; doesn't destructively sleep | `postgresql+asyncpg://USER:PASS@ep-xxx.REGION.aws.neon.tech/db?sslmode=require` |
| Supabase | Free Postgres + dashboard | `postgresql+asyncpg://postgres:PASS@db.xxxx.supabase.co:5432/postgres` |
| Vercel Postgres | Marketplace (Neon under the hood); pairs with the Vercel frontend | copy the string, add `+asyncpg` |

## Migrate (local-first, verify before deploying)
1. Create a DB on the provider, copy its connection string.
2. Put it in `backend/.env` as `DATABASE_URL=postgresql+asyncpg://…` (keep your
   existing `FERNET_KEY` so already-encrypted credentials still decrypt; if the
   old data is gone, users simply re-register).
3. Run the backend locally and confirm:
   ```bash
   uvicorn backend.main:app --reload
   curl localhost:8000/health           # → {"database":"ok"}
   ```
   The app auto-creates the schema on startup (lifespan `create_all`), so a fresh
   empty DB is fine.
4. Smoke-test auth locally: register a user, log in, hit `/auth/me`.

## Then (only when you choose to deploy)
- Set `DATABASE_URL` (and `FERNET_KEY`, `SECRET_KEY`) in the backend host's env.
- The frontend is unchanged — it talks to the backend via `BACKEND_URL`; no DB
  config lives in the frontend.

## Notes
- `FERNET_KEY` encrypts stored platform credentials + LinkedIn cookies. If you
  rotate it (or the old DB is gone), those stored secrets can't be decrypted —
  users re-enter credentials. JWT `SECRET_KEY` derives from `FERNET_KEY` if unset,
  so changing it logs everyone out (expected).
- SQLite is fine for local dev but is per-instance/ephemeral on most hosts — use
  Postgres for any deployed environment.
