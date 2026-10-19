#!/usr/bin/env python3
"""JobAgent MCP server — lets Claude run your whole job search through JobAgent.

Claude (Desktop or Code) talks to this over stdio; it calls the JobAgent API as
you. Standard library only, so any Python 3.8+ runs it.

One-time login (password is prompted, never stored — only a refresh token):
    python3 mcp_server/jobagent_mcp.py login --api https://your-backend --email you@x.com

Then add to Claude:
    claude mcp add jobagent -- python3 /abs/path/mcp_server/jobagent_mcp.py
or in Claude Desktop's claude_desktop_config.json:
    {"mcpServers": {"jobagent": {"command": "python3", "args": ["/abs/path/mcp_server/jobagent_mcp.py"]}}}
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CRED_PATH = os.path.expanduser(os.environ.get("JOBAGENT_CREDENTIALS", "~/.jobagent/credentials.json"))
PROTOCOL_VERSION = "2025-06-18"

# Mission phase numbers (backend PHASE_PLATFORM_MAP).
PHASES = {"linkedin": 1, "internshala": 2, "wellfound": 3, "naukri": 4, "unstop": 5,
          "web_search": 6, "form_fill": 7}


# ── API client ───────────────────────────────────────────────────────────────

class ApiError(Exception):
    pass


class Api:
    def __init__(self):
        try:
            with open(CRED_PATH) as f:
                creds = json.load(f)
        except FileNotFoundError:
            raise ApiError(f"Not logged in. Run: python3 {os.path.abspath(__file__)} login "
                           "--api <backend url> --email <you>")
        self.base = creds["api_url"].rstrip("/")
        self.refresh_token = creds["refresh_token"]
        self.access = None

    def _raw(self, method, path, body=None, token=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                text = r.read().decode()
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            try:
                detail = json.loads(text).get("detail", text)
            except (ValueError, AttributeError):
                detail = text
            return e.code, detail
        except urllib.error.URLError as e:
            raise ApiError(f"Can't reach JobAgent at {self.base}: {e.reason}")

    def _refresh(self):
        status, data = self._raw("POST", "/auth/refresh", {"refresh_token": self.refresh_token})
        if status != 200:
            raise ApiError("JobAgent session expired — run the login command again.")
        self.access, self.refresh_token = data["access_token"], data["refresh_token"]
        _save_creds(self.base, self.refresh_token)  # tokens rotate; keep the newest

    def call(self, method, path, body=None):
        if not self.access:
            self._refresh()
        status, data = self._raw(method, path, body, self.access)
        if status == 401:
            self._refresh()
            status, data = self._raw(method, path, body, self.access)
        if status >= 400:
            raise ApiError(f"{status}: {data if isinstance(data, str) else json.dumps(data)}")
        return data


def _save_creds(api_url, refresh_token):
    os.makedirs(os.path.dirname(CRED_PATH), exist_ok=True)
    fd = os.open(CRED_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"api_url": api_url, "refresh_token": refresh_token}, f)


# ── Tools ────────────────────────────────────────────────────────────────────
# (name, description, input schema, handler(api, args) -> result)

def _q(path, **params):
    params = {k: v for k, v in params.items() if v not in (None, "")}
    return path + ("?" + urllib.parse.urlencode(params) if params else "")


def _phases(args):
    names = args.get("missions") or []
    bad = [n for n in names if n not in PHASES]
    if bad or not names:
        raise ApiError(f"missions must be from {sorted(PHASES)}")
    return [PHASES[n] for n in names]


def _s(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


STR, INT, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}

TOOLS = [
    ("scan_portals",
     "Find ~10 companies hiring for a role archetype, with their career-portal URLs. "
     "Follow with save_mission_targets for the ones worth targeting.",
     _s({"query": {**STR, "description": "Role archetype, e.g. 'business analyst intern, SQL, Bangalore'"},
         "companies": {"type": "array", "items": STR, "description": "Companies to include"}}, ["query"]),
     lambda api, a: api.call("POST", "/career-ops/scan", {"query": a["query"], "companies": a.get("companies") or []})),
    ("save_mission_targets",
     "Save companies (and their portal URLs) as AI Mission targets. The web_search mission searches them first "
     "and pulls every open role from their Greenhouse/Lever boards. Portal URLs are verified; invented ones are skipped.",
     _s({"targets": {"type": "array", "items": _s({"company": STR, "portals": {"type": "array", "items": STR}}, ["company"])}},
        ["targets"]),
     lambda api, a: api.call("POST", "/career-ops/mission-targets", {"targets": a["targets"]})),
    ("list_mission_targets", "Show the saved AI Mission target companies and job boards.", _s({}),
     lambda api, a: api.call("GET", "/career-ops/mission-targets")),
    ("remove_mission_target", "Remove a company from the AI Mission targets.", _s({"company": STR}, ["company"]),
     lambda api, a: api.call("DELETE", "/career-ops/mission-targets/" + urllib.parse.quote(a["company"]))),
    ("tailor_cv",
     "Suggest CV improvements for a job description: summary, keywords, experience rewrites (with the original text). "
     "Nothing is saved — show the user and use apply_cv_tailoring for what they approve.",
     _s({"jd_text": STR}, ["jd_text"]),
     lambda api, a: api.call("POST", "/career-ops/tailor-cv", {"jd_text": a["jd_text"]})),
    ("apply_cv_tailoring",
     "Save approved tailor_cv suggestions to the user's profile; every AI Mission then uses them. Only include "
     "skills the user confirmed they have. Undo with undo_cv_tailoring.",
     _s({"summary": STR, "skills_add": {"type": "array", "items": STR},
         "rewrites": {"type": "array", "items": _s({"experience_index": INT, "rewrite": STR},
                                                    ["experience_index", "rewrite"])}}),
     lambda api, a: api.call("POST", "/career-ops/tailor-cv/apply",
                             {"summary": a.get("summary"), "skills_add": a.get("skills_add") or [],
                              "rewrites": a.get("rewrites") or []})),
    ("undo_cv_tailoring", "Restore the profile as it was before the last apply_cv_tailoring.", _s({}),
     lambda api, a: api.call("POST", "/career-ops/tailor-cv/undo")),
    ("launch_mission",
     "Start AI Missions that find and apply to jobs. missions: any of linkedin, internshala, wellfound, naukri, "
     "unstop, web_search, form_fill. Use dry_run first if the user hasn't run one before.",
     _s({"missions": {"type": "array", "items": {"type": "string", "enum": sorted(PHASES)}},
         "dry_run": {**BOOL, "description": "Find and fill without submitting"}}, ["missions"]),
     lambda api, a: api.call("POST", "/agents/run", {"phases": _phases(a), "dry_run": bool(a.get("dry_run"))})),
    ("mission_status", "Recent AI Mission runs with status and applied/skipped counts.", _s({}),
     lambda api, a: api.call("GET", "/agents/runs")),
    ("mission_logs", "Log lines from one mission run.", _s({"run_id": STR}, ["run_id"]),
     lambda api, a: api.call("GET", f"/agents/runs/{urllib.parse.quote(a['run_id'])}/logs")),
    ("stop_mission", "Stop a running mission.", _s({"run_id": STR}, ["run_id"]),
     lambda api, a: api.call("POST", f"/agents/pause/{urllib.parse.quote(a['run_id'])}")),
    ("list_applications", "Tracked applications, newest first.",
     _s({"status": {"type": "string", "enum": ["applied", "viewed", "shortlisted", "interview", "offer", "rejected"]},
         "search": {**STR, "description": "Company or title contains"}, "limit": INT}),
     lambda api, a: api.call("GET", _q("/jobs", status=a.get("status"), search=a.get("search"),
                                       limit=a.get("limit") or 50))),
    ("record_outcome",
     "Update an application's status (e.g. after reading an interview invite or rejection in the user's email). "
     "Put the evidence or interviewer feedback in note — it feeds the next round's interview prep.",
     _s({"application_id": STR,
         "status": {"type": "string", "enum": ["applied", "viewed", "shortlisted", "interview", "offer", "rejected"]},
         "note": STR}, ["application_id", "status"]),
     lambda api, a: api.call("PATCH", f"/jobs/{urllib.parse.quote(a['application_id'])}/status",
                             {"status": a["status"], "note": a.get("note") or ""})),
    ("interview_prep", "Interview prep for an application, built from the resume and note actually submitted.",
     _s({"application_id": STR}, ["application_id"]),
     lambda api, a: api.call("GET", f"/jobs/{urllib.parse.quote(a['application_id'])}/interview-prep")),
    ("followups_due", "Applications that have gone quiet past their follow-up cadence.", _s({}),
     lambda api, a: api.call("GET", "/career-ops/followups/due")),
    ("draft_followup",
     "Draft (never send) a follow-up for an application from followups_due. Max 2 per application.",
     _s({"application_id": STR, "company": STR, "role": STR,
         "status": {"type": "string", "enum": ["applied", "responded", "interview"]},
         "days_since_action": INT, "last_message": STR},
        ["application_id", "company", "role", "status", "days_since_action"]),
     lambda api, a: api.call("POST", "/career-ops/followup", a)),
    ("skill_gaps", "Skills employers asked for that the user's profile lacked, weighted by frequency.", _s({}),
     lambda api, a: api.call("GET", "/career-ops/skill-gaps")),
    ("study_plan", "Learning plan for the skill gaps, with free resources and a proof project each.",
     _s({"hours_per_week": INT}),
     lambda api, a: api.call("POST", "/career-ops/skill-gaps/plan", {"hours_per_week": a.get("hours_per_week") or 6})),
    ("evaluate_offer", "Grade a job description A–G against the user's CV and recommend apply / tailor first / skip.",
     _s({"jd_text": STR, "company": STR, "role": STR, "url": STR}, ["jd_text"]),
     lambda api, a: api.call("POST", "/career-ops/evaluate", a)),
]
_BY_NAME = {t[0]: t for t in TOOLS}


# ── MCP over stdio (JSON-RPC 2.0, one message per line) ─────────────────────

def handle(msg, state):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification (e.g. notifications/initialized) — no reply
        return None
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": version, "capabilities": {"tools": {}},
            "serverInfo": {"name": "jobagent", "version": "1.0.0"},
            "instructions": "JobAgent automates the user's job search. Typical flow: scan_portals → "
                            "save_mission_targets → tailor_cv/apply_cv_tailoring (with the user's approval) → "
                            "launch_mission → mission_status → record_outcome / followups_due / interview_prep. "
                            "Ask before launching a non-dry-run mission: it submits real applications."}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": s} for n, d, s, _ in TOOLS]}}
    if method == "tools/call":
        params = msg.get("params") or {}
        tool = _BY_NAME.get(params.get("name"))
        if not tool:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool {params.get('name')}"}}
        try:
            if "api" not in state:
                state["api"] = Api()
            result = tool[3](state["api"], params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=1, default=str)}]}}
        except (ApiError, KeyError, ValueError) as e:
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve(stdin=sys.stdin, stdout=sys.stdout):
    state = {}
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(msg, state)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def login(api_url, email):
    api_url = api_url.rstrip("/")
    password = getpass.getpass(f"JobAgent password for {email}: ")
    req = urllib.request.Request(api_url + "/auth/login", method="POST",
                                 data=json.dumps({"email": email, "password": password}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Login failed ({e.code}): {e.read().decode(errors='replace')[:200]}")
    _save_creds(api_url, data["refresh_token"])
    print(f"Logged in. Refresh token saved to {CRED_PATH} (readable only by you).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    lg = sub.add_parser("login", help="Log in once and store a refresh token")
    lg.add_argument("--api", required=True, help="JobAgent backend URL")
    lg.add_argument("--email", required=True)
    args = p.parse_args()
    if args.cmd == "login":
        login(args.api, args.email)
    else:
        serve()
