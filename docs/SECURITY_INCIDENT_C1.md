# SECURITY INCIDENT C1 — Leaked user database

**Severity:** Critical · **Status:** code-side remediated; operator actions REQUIRED below.

## What happened
`jobagent.db` (a SQLite database with **6 real user accounts** — bcrypt password hashes,
Fernet-encrypted platform credentials + LinkedIn session cookies, emails, payment rows) was committed
and tracked in the repository, which has a public GitHub remote
(`github.com/Hraghuwa/job-autoapplier-ai-latest`). `.gitignore` listed the file, but it had been
committed *before* that rule, so git kept tracking it.

## Done in code (this branch: `audit-remediation`)
- `git rm --cached jobagent.db` — removed from the index; local file kept; `.gitignore` already ignores
  `*.db`, `backend.db`, `jobagent.db`, so it will not be re-added.

## Operator MUST do (cannot be automated from here — needs secrets / force-push)
1. **Assume the DB contents are public.** Treat every stored credential and session cookie as compromised.
2. **Rotate `FERNET_KEY`** in the Railway environment. ⚠️ This invalidates all existing
   Fernet-encrypted values (platform passwords, LinkedIn cookies) — users must re-enter credentials.
   Because `SECRET_KEY` is *derived from* `FERNET_KEY` (backend/config.py), rotating Fernet also rotates
   JWT signing → all sessions are invalidated (acceptable; forces re-login). Consider also setting
   `SECRET_KEY` explicitly so the two secrets are independent going forward.
3. **Invalidate stored platform credentials & LinkedIn cookies** for the 6 users (null the
   `platform_passwords` columns) so the old, possibly-decryptable values can't be reused. Prompt re-entry.
4. **Scrub git history** so the blob is unreachable even from old commits:
   ```bash
   # with git-filter-repo (preferred)
   git filter-repo --invert-paths --path jobagent.db --path backend.db
   # then force-push all branches/tags
   git push origin --force --all && git push origin --force --tags
   ```
   (Do NOT run history rewrite unilaterally — coordinate; it changes every downstream clone.)
5. **Notify the 6 affected users** of the exposure and the forced credential reset (GDPR/CCPA breach
   notice may apply).
6. **Going forward:** move the dev datastore out of the repo tree (e.g. `~/.local/share/jobagent/…` or a
   `data/` dir that is gitignored), and add a pre-commit hook blocking `*.db`/secret patterns.

## Why history scrub matters
`git rm --cached` only stops *future* tracking. The blob remains in history and on GitHub until history
is rewritten and force-pushed, and GitHub may retain cached views — assume the data is already harvested
and prioritize rotation/notification over the scrub.
