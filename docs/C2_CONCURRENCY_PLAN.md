# C2 / M5 — Concurrency migration (IMPLEMENTED on branch `c2-concurrency`)

> **Status: implemented; pending live end-to-end verification.** The subprocess
> design below is now built (branch `c2-concurrency`). What IS verified here:
> the stdout→event classifier is extracted and unit-tested (9 tests), the full
> suite is green (65 passed), and the subprocess runner's setup/teardown path
> (config load, sys.path, SQLite session factory, result-file write) runs
> cleanly in a smoke test. What is NOT yet verified (no Chrome/Redis/LLM stack
> in this environment): an actual phase driving a browser, live WS streaming,
> Redis-based stop, and true concurrent runs. **Do a manual end-to-end run per
> phase on a real stack before merging — see Acceptance below.** The legacy
> in-process path is preserved behind `JOBAGENT_INPROC_PHASE=1` as an escape
> hatch if the subprocess path misbehaves in production.

## What shipped
- `backend/workers/agent_tasks.py`: `classify_agent_line()` (pure, tested);
  `_execute_subprocess()` (default) and `_execute_inproc()` (escape hatch);
  `_run_phase_logic()` now orchestrates load/quota/status → executor → bookkeeping,
  with a shared `_handle_line` classifier callback. The global `_config_lock`
  and global `sys.stdout` swap are gone from the default path.
- `agents/run_phase_subprocess.py`: runs one phase in its own interpreter; owns
  the DB session factory, cookie-saver, and a Redis-fed stop event; writes
  `{"applied": n}` to a result file.
- `tests/career_pipeline/test_agent_line_classifier.py`: 9 tests pinning the
  classifier (incl. the login_challenge-beats-error ordering).

## The problem (recap)
`backend/workers/agent_tasks.py::_run_phase_logic`:
- monkey-patches the module-global `agents/config.py::CONFIG`,
- replaces process-global `sys.stdout` with `AgentStdout` to scrape applier prints,
- runs the whole phase inside a single process-global `_config_lock`.

Consequences:
- **C2:** only ONE run executes at a time across the entire backend, regardless of
  Celery `--concurrency`. Throughput ceiling = 1.
- **M5:** the Redis-down fallback (`routers/agents.py`) runs this same code in a
  daemon thread *inside uvicorn*, so it swaps the web process's stdout and holds
  the lock → degrades the API itself.

Root cause: appliers do `from config import CONFIG` at import time → shared mutable
module global → the only safe way to multiplex it is mutual exclusion.

## Recommended fix: run each phase in its own subprocess
Full process isolation is lower-risk than threading and removes globals from the
parent entirely.

1. Add `agents/run_phase_subprocess.py`:
   - `argv`: `<config_json_path> <phase> <run_id>`.
   - Load config from the JSON file into `config.CONFIG` (this process owns its
     own module global — no lock, no cross-talk).
   - Run the phase function; print progress to stdout as today.
2. In `_run_phase_logic`:
   - Build the config dict (unchanged), write the **serializable** subset to a
     temp JSON (drop `_session_factory`, `_stop_event`, `_save_linkedin_cookies`
     — see below).
   - `Popen([...])` and read stdout line-by-line in the parent → run the existing
     `AgentStdout` classifier on each line and `publish()` (the parent keeps its
     own real stdout; no global swap).
   - Drop `_config_lock` entirely — isolation makes it unnecessary.
3. Re-establish the non-serializable bits inside the subprocess:
   - **DB session factory:** rebuild from `DATABASE_URL` (it already does this in
     `_sync_session`).
   - **Stop signal:** already supported cross-process via Redis `pause:{run_id}`
     (`is_stopping()` checks it). Drop the in-memory `threading.Event`.
   - **Cookie refresh callback:** replace the closure with a tiny DB write in the
     subprocess keyed by `user_id` (the logic already exists inline).
4. Per-run Chrome profile: key the profile dir by `run_id` (not just `user_id`)
   so two runs for the same user can't collide — now possible because they're
   separate processes.
5. Concurrency: set Celery `--concurrency=N`; each task spawns one subprocess.
   The rate limiter is already Redis-backed (C3) so caps stay correct across them.

## Acceptance (must verify on a live stack)
- Two users' phase-1 runs proceed **concurrently** (overlapping timestamps in
  `agent_logs`), neither blocking the other.
- WebSocket events still stream (applied/skipped/login_challenge classify correctly).
- Stop/pause still halts a run (via Redis key).
- Server runs close Chrome (N1) — no leaked processes after N runs.
- The 56-test baseline stays green; add an integration test that spawns the
  subprocess against a fake phase fn and asserts stdout→event classification.

## Smaller interim option (if subprocess work must wait)
Keep the lock but **narrow its scope** to only the CONFIG setup, and give each
applier its config via a function arg instead of the module global — but this
touches every applier and is itself large. The subprocess route is cleaner.
