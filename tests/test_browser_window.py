"""Background vs visible agent browser (the "Show browser" toggle).

Background = a real (non-headless) Chrome parked off-screen that never takes
focus from the user, still passes bot checks, and isn't throttled while hidden.
Nothing pops up unless the user turned on "Show browser".
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents")))

import browser_window
from browser_window import window_args, send_to_background, needs_you


def test_background_parks_window_off_screen():
    args = window_args(show_browser=False)
    assert "--window-position=-32000,-32000" in args
    assert "--start-maximized" not in args


def test_background_is_not_headless():
    # Headless trips LinkedIn/Naukri bot checks; off-screen keeps a real window.
    assert not any(a.startswith("--headless") for a in window_args(False))


def test_background_is_not_throttled():
    args = window_args(False)
    for flag in ("--disable-backgrounding-occluded-windows",
                 "--disable-renderer-backgrounding",
                 "--disable-background-timer-throttling"):
        assert flag in args


def test_visible_shows_window_on_screen():
    args = window_args(show_browser=True)
    assert not any(a.startswith("--window-position=-") for a in args)


class _FakeDriver:
    def __init__(self, fail=False, browser_pid=None):
        self.pos, self.fail = None, fail
        if browser_pid:
            self.browser_pid = browser_pid

    def set_window_position(self, x, y):
        if self.fail:
            raise RuntimeError("window gone")
        self.pos = (x, y)


@pytest.fixture(autouse=True)
def _never_spawn_real_guard(monkeypatch):
    monkeypatch.setattr(browser_window, "_start_guard", lambda: None)


def _no_guard(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(browser_window, "_REGISTRY", str(tmp_path / "pids"))
    monkeypatch.setattr(browser_window, "_start_guard", lambda: started.append(1))
    monkeypatch.setattr(browser_window.sys, "platform", "darwin")
    return started


def test_send_to_background_moves_window_after_launch(monkeypatch, tmp_path):
    # macOS clamps the --window-position launch flag (a sliver stays visible);
    # a post-launch move goes fully off-screen.
    _no_guard(monkeypatch, tmp_path)
    d = _FakeDriver()
    send_to_background(d, show_browser=False)
    assert d.pos == (-32000, -32000)


def test_send_to_background_registers_chrome_and_guards_focus(monkeypatch, tmp_path):
    # Chrome grabs focus on launch and on every tab switch; the guard hands it back.
    started = _no_guard(monkeypatch, tmp_path)
    send_to_background(_FakeDriver(browser_pid=4242), show_browser=False)
    assert "4242" in (tmp_path / "pids").read_text().split()
    assert started == [1]


def test_send_to_background_noop_when_visible(monkeypatch, tmp_path):
    started = _no_guard(monkeypatch, tmp_path)
    d = _FakeDriver(browser_pid=4242)
    send_to_background(d, show_browser=True)
    assert d.pos is None and started == []
    send_to_background(_FakeDriver(fail=True), show_browser=False)  # never raises


class _CdpDriver(_FakeDriver):
    """Records commands like a selenium driver's execute / execute_cdp_cmd."""
    def __init__(self):
        super().__init__(browser_pid=4242)
        self.cdp = []

    def execute(self, command, params=None):
        return {"value": None}

    def execute_cdp_cmd(self, cmd, args):
        self.cdp.append((cmd, args))


def test_hidden_pages_still_render_after_tab_switch(monkeypatch, tmp_path):
    # A hidden Chrome reports visibilityState=hidden and stalls rAF/transitions,
    # which can freeze animated apply modals. Focus emulation keeps every tab
    # the agent works in "visible" — re-applied whenever it switches/opens a tab.
    _no_guard(monkeypatch, tmp_path)
    d = _CdpDriver()
    send_to_background(d, show_browser=False)
    focus = ("Emulation.setFocusEmulationEnabled", {"enabled": True})
    focus_calls = lambda: [c for c in d.cdp if c[0] == focus[0]]
    assert focus_calls() == [focus]
    d.execute("switchToWindow", {"handle": "t2"})
    d.execute("newWindow", {"type": "tab"})
    d.execute("get", {"url": "https://x"})
    assert focus_calls() == [focus, focus, focus]


def test_site_popups_become_tabs_in_every_tab(monkeypatch, tmp_path):
    # A site popup (window.open with width/height) opens a NEW on-screen window
    # and activates Chrome over the user's app. Dropping the features makes it a
    # tab in the hidden off-screen window. Re-applied per tab, like focus.
    _no_guard(monkeypatch, tmp_path)
    d = _CdpDriver()
    send_to_background(d, show_browser=False)
    popup = lambda: [c for c in d.cdp if c[0] == "Page.addScriptToEvaluateOnNewDocument"]
    assert len(popup()) == 1 and "window.open" in popup()[0][1]["source"]
    d.execute("switchToWindow", {"handle": "t2"})
    assert len(popup()) == 2


def test_popup_script_drops_window_features():
    import json
    import subprocess
    js = f"""
    const calls = [];
    globalThis.window = {{ open: (...a) => {{ calls.push(a); return 'w'; }} }};
    {browser_window._POPUPS_AS_TABS_JS}
    const r = window.open('https://apply.example', 'pop', 'width=600,height=500');
    console.log(JSON.stringify({{calls, r}}));
    """
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert out == {"calls": [["https://apply.example", "_blank"]], "r": "w"}


def test_guard_returns_focus_to_the_users_previous_app():
    # A hide makes macOS activate a random app ~0.3 s later, which the guard
    # then took for the user's (seen: Claude instead of TextEdit). The guard
    # re-activates the most recent non-agent app and never hides.
    js = browser_window._GUARD_JS
    assert "activateWithOptions" in js and "recent" in js
    assert ".hide" not in js


def test_guard_starts_before_chrome_launches(monkeypatch, tmp_path):
    # Chrome steals focus while launching; the guard must already know the user's app.
    started = _no_guard(monkeypatch, tmp_path)
    window_args(show_browser=False)
    assert started == [1]
    window_args(show_browser=True)
    assert started == [1]


def test_no_focus_guard_off_macos(monkeypatch, tmp_path):
    started = _no_guard(monkeypatch, tmp_path)
    monkeypatch.setattr(browser_window.sys, "platform", "linux")
    send_to_background(_FakeDriver(browser_pid=4242), show_browser=False)
    assert started == []


def test_needs_you_never_touches_the_window_in_background(capsys):
    # A CAPTCHA must not pop the browser over the user's work — log it instead.
    needs_you({"show_browser": False})
    assert "Show browser" in capsys.readouterr().out


def test_needs_you_silent_when_window_already_visible(capsys):
    needs_you({"show_browser": True})
    assert capsys.readouterr().out == ""


def test_registry_drops_dead_pids(monkeypatch, tmp_path):
    # macOS reuses PIDs: a stale entry could later match one of the user's apps.
    _no_guard(monkeypatch, tmp_path)
    (tmp_path / "pids").write_text(f"999999\n{os.getpid()}\n")
    send_to_background(_FakeDriver(browser_pid=4242), show_browser=False)
    pids = (tmp_path / "pids").read_text().split()
    assert "999999" not in pids and str(os.getpid()) in pids


def test_guard_only_ever_hides_chrome():
    assert "chrome" in browser_window._GUARD_JS.lower()
    assert "bundleIdentifier" in browser_window._GUARD_JS


def test_guard_sees_the_live_front_app():
    # In a JXA loop, NSWorkspace.frontmostApplication only refreshes when the run
    # loop runs; delay() froze it at its first value (guard either hid the agent
    # forever, bouncing the user between apps, or never acted). Spin the run loop.
    js = browser_window._GUARD_JS
    assert "runUntilDate" in js and "delay(" not in js
