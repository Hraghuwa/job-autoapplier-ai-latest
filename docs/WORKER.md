# Agent worker — runtime requirements

The Celery worker (and the web-process in-thread fallback) run the appliers,
which drive a real browser. That needs **two** things the lean API image lacks —
their absence is what produced `No module named 'selenium'` and "0 applications":

1. **Python browser deps** — `selenium`, `webdriver-manager`,
   `undetected-chromedriver`. Now in `requirements.txt`, so any environment that
   installs backend deps has them.
2. **A Chrome/Chromium binary + matching chromedriver** — `selenium` alone can't
   launch a browser. Provided by `backend/Dockerfile.worker`
   (`chromium` + `chromium-driver`), which also sets `CHROME_BIN` and
   `CHROMEDRIVER_PATH` so `create_driver` uses the distro browser instead of a
   runtime webdriver-manager download.

## Running the worker
- **docker-compose** (recommended): the `worker` service builds from
  `backend/Dockerfile.worker` — `docker compose up --build worker`.
- **Bare/host**: `pip install -r requirements-agents.txt`, ensure Chrome or
  Chromium is installed, then `./start_worker.sh` (or
  `celery -A backend.workers.celery_app worker -Q agents,default`).
- **Other PaaS**: install `requirements.txt` (selenium included) **and** a Chrome
  binary in the worker; set `CHROME_BIN` / `CHROMEDRIVER_PATH` if not at the
  default `/usr/bin/chromium` paths.

## Verify readiness before running
`GET /agents/healthcheck` now reports both:
```json
{"selenium": true, "chrome_binary": true, "ok": true, ...}
```
`ok` is true only when selenium is importable AND a Chrome binary is present —
so a misconfigured worker is visible up front instead of failing mid-run.

## Notes
- The API image (`backend/Dockerfile`) intentionally stays lean; only the worker
  needs the browser stack. The escape hatch `JOBAGENT_INPROC_PHASE=1` runs phases
  in the web process — that process then also needs selenium + Chrome.
