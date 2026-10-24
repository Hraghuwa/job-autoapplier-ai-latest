"""Chrome window handling for the "Show browser" toggle.

Background (default): a real, non-headless Chrome parked off-screen that never
takes focus from the user's work. Headless is avoided on purpose — it trips
LinkedIn / Naukri bot checks. The anti-throttling flags keep a hidden window
running at full speed; progress is visible in the run's live logs.
Nothing pops up or steals focus unless the user turns on "Show browser".
"""
import os
import subprocess
import sys
import tempfile

OFF_SCREEN = "--window-position=-32000,-32000"

_NO_THROTTLE = [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]

# Every background agent Chrome on this machine, shared by all agent processes
# so their focus guards agree on what "agent Chrome" is (no ping-pong).
_REGISTRY = os.path.join(tempfile.gettempdir(), "jobagent_background_chrome.pids")
_guard = None

# macOS: Chrome activates itself on launch, tab switches and new windows. This
# loop hides an agent Chrome the moment it becomes frontmost and re-activates
# the app the user was last in (hiding alone lets macOS pick any app — seen: the
# user's own Chrome instead of Outlook). In-process AppKit calls via JXA — no
# Automation/Accessibility permission needed. Exits when its parent (the agent
# process) dies.
_GUARD_JS = r"""
ObjC.import('AppKit'); ObjC.import('signal');
function run(argv) {
  const reg = argv[0], parent = Number(argv[1]);
  let last = null;
  while ($.kill(parent, 0) === 0) {
    const front = $.NSWorkspace.sharedWorkspace.frontmostApplication;
    if (front && !front.isNil()) {
      const txt = $.NSString.stringWithContentsOfFileEncodingError(reg, 4, null);
      const agents = txt.isNil() ? [] : ObjC.unwrap(txt).split(/\s+/).filter(Boolean).map(Number);
      const bundle = ObjC.unwrap(front.bundleIdentifier) || '';
      if (agents.indexOf(front.processIdentifier) >= 0 && /chrome/i.test(bundle)) {
        front.hide;
        if (last && !last.terminated) last.activateWithOptions(0);
      } else {
        last = front;
      }
    }
    // Spin the run loop (a plain sleep freezes frontmostApplication at its first value).
    $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.05));
  }
}
"""

# Sites open "Apply" / sign-in popups with window.open(url, name, "width=..").
# Those become NEW on-screen windows (the off-screen launch position only
# applies to the first window) and activate Chrome over the user's work.
# Dropping the features turns them into tabs inside the hidden window.
_POPUPS_AS_TABS_JS = """
(() => {
  const open = window.open;
  window.open = function (url) { return open.call(window, url, '_blank'); };
})();
"""


def window_args(show_browser: bool) -> list:
    if show_browser:
        return ["--window-position=50,50"]
    return [OFF_SCREEN, *_NO_THROTTLE]


def show_browser(config: dict) -> bool:
    return bool((config or {}).get("show_browser", False))


def _browser_pids(driver) -> list:
    pid = getattr(driver, "browser_pid", None)  # undetected-chromedriver
    if pid:
        return [int(pid)]
    try:  # selenium: Chrome is a child of chromedriver
        out = subprocess.run(["pgrep", "-P", str(driver.service.process.pid)],
                             capture_output=True, text=True, timeout=5).stdout
        return [int(p) for p in out.split()]
    except Exception:
        return []


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _register(pids) -> None:
    """Add agent Chrome PIDs, dropping dead ones (macOS reuses PIDs)."""
    try:
        with open(_REGISTRY) as f:
            old = [int(p) for p in f.read().split() if p.isdigit()]
    except OSError:
        old = []
    keep = [p for p in old if _alive(p)] + [p for p in pids if p not in old]
    # ponytail: unlocked read-modify-write; two agents launching in the same ms
    # could drop one entry (that Chrome just isn't guarded) — add flock if seen.
    with open(_REGISTRY, "w") as f:
        f.write("".join(f"{p}\n" for p in keep))


def _start_guard() -> None:
    global _guard
    if _guard is None or _guard.poll() is not None:
        _guard = subprocess.Popen(["osascript", "-l", "JavaScript", "-e", _GUARD_JS,
                                   _REGISTRY, str(os.getpid())],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_FOCUS_EMULATION = ("Emulation.setFocusEmulationEnabled", {"enabled": True})
_TAB_COMMANDS = ("switchToWindow", "newWindow")


def _keep_pages_visible(driver) -> None:
    """A hidden Chrome reports visibilityState=hidden and stalls rAF/CSS transitions,
    which can freeze animated apply modals. Focus emulation keeps the tab the
    agent works in "visible"; it is per-tab, so re-apply on every tab switch/open.
    """
    def focus():
        try:
            driver.execute_cdp_cmd(*_FOCUS_EMULATION)
            # Applies to the tab's next page loads; agents navigate after switching.
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                                   {"source": _POPUPS_AS_TABS_JS})
        except Exception:
            pass

    execute = getattr(driver, "execute", None)
    if execute is None:
        return

    def execute_and_refocus(command, params=None):
        result = execute(command, params)
        if command in _TAB_COMMANDS:
            focus()
        return result

    driver.execute = execute_and_refocus
    focus()


def send_to_background(driver, show_browser: bool) -> None:
    """Right after launch: move the window fully off-screen and stop it stealing focus.

    macOS clamps the --window-position launch flag and leaves a sliver of the
    window visible; a post-launch move lands fully off-screen.
    """
    if show_browser:
        return
    try:
        driver.set_window_position(-32000, -32000)
    except Exception:
        pass
    # ponytail: focus guard is macOS-only; add a Windows equivalent if agents run there.
    if sys.platform != "darwin":
        return
    pids = _browser_pids(driver)
    if not pids:
        return
    _keep_pages_visible(driver)
    try:
        _register(pids)
        _start_guard()
    except Exception:
        pass


def needs_you(config: dict) -> None:
    """A CAPTCHA/login needs a human. Never pops the window over the user's work."""
    if show_browser(config):
        return
    print("  👀 Action needed, but the browser is running in the background. "
          "Turn on 'Show browser' on the Automation page and relaunch to solve it, "
          "or save LinkedIn cookies so no challenge appears.")
