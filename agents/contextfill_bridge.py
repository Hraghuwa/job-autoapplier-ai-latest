"""Drive the ContextFill extension (github.com/Hraghuwa/contextfill) from Selenium (ADR-001).

Branded Chrome >=137 ignores --load-extension, so a ContextFill run uses Chrome
for Testing (Selenium Manager downloads it when browser_version != installed).
The agent keeps one "control" tab on the extension's options page — extension
pages can call chrome.storage / chrome.tabs / runtime.sendMessage, which is how
we seed the profile and ask the background worker to fill a given tab.
"""
import base64
import hashlib
import os

DEFAULT_DIR = os.path.expanduser("~/contextfill")


def extension_dir(config):
    d = (config or {}).get("contextfill_dir") or os.environ.get("CONTEXTFILL_DIR") or DEFAULT_DIR
    d = os.path.realpath(os.path.expanduser(d))
    return d if os.path.isfile(os.path.join(d, "manifest.json")) else None


def extension_id(path):
    """Chrome's id for an unpacked extension = sha256(path)[:32] mapped 0-f → a-p."""
    return "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(path.encode()).hexdigest()[:32])


def add_to_options(opts, config):
    """Configure Chrome options to load ContextFill. Returns the extension id or None."""
    d = extension_dir(config)
    if not d:
        return None
    opts.browser_version = os.environ.get("CONTEXTFILL_CHROME", "beta")  # Chrome for Testing
    opts.add_argument(f"--load-extension={d}")
    return extension_id(d)


def _profile(config):
    """JobAgent profile → ContextFill's profile schema (llm.js PROFILE_FIELDS/LIST_FIELDS)."""
    c = config or {}
    p = c.get("profile") or {}
    full = str(p.get("full_name") or c.get("name") or "").strip()
    first, _, last = full.partition(" ")
    loc = str(p.get("location") or (c.get("locations") or [""])[0])

    def _list(v):
        return v if isinstance(v, list) else []

    exp = []
    for e in _list(p.get("experiences")) or _list(p.get("experience")):
        if isinstance(e, dict):
            exp.append({"company": str(e.get("company", "")), "title": str(e.get("role") or e.get("title", "")),
                        "type": "Full-time", "location": str(e.get("location", "")),
                        "start": str(e.get("start", "")), "end": str(e.get("end", "")),
                        "description": " ".join(str(b.get("text", b) if isinstance(b, dict) else b)
                                                for b in _list(e.get("bullets"))) or str(e.get("description", ""))})
    edu = []
    for e in _list(p.get("education")):
        if isinstance(e, dict):
            edu.append({"level": str(e.get("level", "")), "degree": str(e.get("degree", "")),
                        "institution": str(e.get("institution") or e.get("school", "")), "board": "",
                        "startYear": str(e.get("start", "")), "endYear": str(e.get("end") or e.get("year", "")),
                        "score": str(e.get("score") or e.get("cgpa", "")), "status": ""})
    if not edu and p.get("university"):
        edu.append({"level": "UG", "degree": str(p.get("degree", "")), "institution": str(p["university"]),
                    "board": "", "startYear": str(p.get("enrollment_year", "")),
                    "endYear": str(p.get("graduation_year", "")), "score": str(p.get("graduation_cgpa", "")),
                    "status": ""})
    summary = str(p.get("summary") or p.get("experience_summary") or "")
    skills = p.get("skills")
    if skills:
        summary += "\nSkills: " + (", ".join(map(str, skills)) if isinstance(skills, list) else str(skills))
    return {
        "firstName": first, "lastName": last, "email": str(p.get("email") or c.get("email") or ""),
        "altEmail": "", "phone": str(p.get("phone") or c.get("phone") or ""),
        "city": loc, "country": "India", "linkedin": str(p.get("linkedin", "")), "github": "", "website": "",
        "currentTitle": str(p.get("current_role", "")), "currentCompany": str(p.get("current_company", "")),
        "yearsExperience": str(p.get("years_of_experience", "")),
        "workAuthorization": "", "needsSponsorship": "", "salaryExpectation": "", "noticePeriod": "",
        "summary": summary.strip(), "resumeText": str(p.get("experience") if isinstance(p.get("experience"), str) else ""),
        "education": edu, "experience": exp,
    }


def _llm(config):
    c = config or {}
    if c.get("groq_api_key"):
        return {"provider": "groq", "keys": {"groq": c["groq_api_key"]}, "models": {}}
    # ponytail: local Ollama fallback is ~2 min/form; a Groq key makes fills take seconds.
    return {"provider": "ollama", "keys": {}, "models": {"ollama": os.environ.get("CONTEXTFILL_OLLAMA_MODEL", "gemma4")}}


class ContextFill:
    def __init__(self, driver, ext_id):
        self.driver = driver
        self.ext_id = ext_id
        self.control = None

    def _js(self, body, *args, timeout=30):
        """Run async JS in the control tab; `done` is the callback."""
        self.driver.switch_to.window(self.control)
        self.driver.set_script_timeout(timeout)
        return self.driver.execute_async_script(
            "const done = arguments[arguments.length - 1];"
            "(async () => {" + body + "})().then(done, e => done({error: String(e && e.message || e)}));", *args)

    def setup(self, config):
        """Open the control tab and seed profile, provider and resume. True on success."""
        d = self.driver
        home = d.current_window_handle
        try:
            return self._setup(config)
        finally:
            d.switch_to.window(home)  # never let callers navigate the control tab away

    def _setup(self, config):
        d = self.driver
        d.switch_to.new_window("tab")
        d.get(f"chrome-extension://{self.ext_id}/options.html")
        if "ContextFill" not in (d.title or ""):
            return False
        self.control = d.current_window_handle
        data = {"profile": _profile(config), "llm": _llm(config),
                # JobAgent's question→answer bank doubles as ContextFill's remembered answers.
                "answers": {str(k): str(v) for k, v in ((config or {}).get("autofill_bank") or {}).items() if v}}
        path = (config or {}).get("resume_path") or ""
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                data["resume"] = {"name": os.path.basename(path), "type": "application/pdf",
                                  "data": base64.b64encode(f.read()).decode()}
        r = self._js("await chrome.storage.local.set(arguments[0]); return {ok: true};", data)
        return bool(r and r.get("ok"))

    def open(self, url):
        """Open url in a new tab; returns (window_handle, chrome_tab_id)."""
        before = set(self.driver.window_handles)
        r = self._js(
            "const t = await chrome.tabs.create({url: arguments[0], active: true});"
            "for (let i = 0; i < 60; i++) { const x = await chrome.tabs.get(t.id);"
            "  if (x.status === 'complete') break; await new Promise(s => setTimeout(s, 500)); }"
            "return {id: t.id};", url, timeout=45)
        new = [h for h in self.driver.window_handles if h not in before]
        handle = new[0] if new else None
        if handle:
            self.driver.switch_to.window(handle)
        return handle, (r or {}).get("id")

    def active_tab_id(self, handle):
        """Chrome tab id of a Selenium handle (after Apply opened a new tab)."""
        self.driver.switch_to.window(handle)
        title, url = self.driver.title, self.driver.current_url
        r = self._js("const ts = await chrome.tabs.query({});"
                     "const t = ts.find(t => t.url === arguments[0]) || ts.find(t => t.title === arguments[1]);"
                     "return {id: t ? t.id : null};", url, title)
        return (r or {}).get("id")

    def fill(self, tab_id, timeout=300):
        """Ask ContextFill to fill a tab. Returns {filled, asks[], error}."""
        r = self._js("return await chrome.runtime.sendMessage({type: 'fill', tabId: arguments[0]});",
                     tab_id, timeout=timeout) or {}
        return {"filled": r.get("filled", 0), "asks": r.get("asks") or [], "error": r.get("error", "")}
