# C2 / M5 — Concurrency migration plan (NOT yet implemented)

> **Status: design only.** This is the audit's rank-9 item. It is deliberately
> NOT implemented in the remediation branch because it cannot be verified here:
> there is no runnable Chrome/Redis/DB-with-data/LLM stack, and the test suite
> (56 tests) exercises the resume pipeline + services — **none of the worker
> runtime**. A blind rewrite would risk an unverifiable production regression,
> which Phase 9 of the audit forbids. Implement this with a live stack + manual
> end-to-end run per phase.

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
