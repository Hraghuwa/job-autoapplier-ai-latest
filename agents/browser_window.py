"""Chrome window handling for the "Show browser" toggle.

Background (default): a real, non-headless Chrome parked off-screen that never
takes focus from the user's work. Headless is avoided on purpose — it trips
LinkedIn / Naukri bot checks. The anti-throttling flags keep a hidden window
running at full speed; progress is visible in the run's live logs.
Nothing pops up or steals focus unless the user turns on "Show browser".
"""
import hashlib
import os
import select
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
# loop re-activates the app the user was last in the moment an agent Chrome
# becomes frontmost. It starts before Chrome launches so it already knows that
# app. No hide: a hide is async and makes macOS activate yet another app ~0.3 s
# later, which the guard then mistook for the user's app (seen: Claude instead
# of TextEdit). In-process AppKit calls via JXA — no Automation/Accessibility
# permission needed. Exits when its parent (the agent process) dies.
_GUARD_JS = r"""
ObjC.import('AppKit'); ObjC.import('signal');
function run(argv) {
  const reg = argv[0], parent = Number(argv[1]);
  // Recent non-agent front apps, newest first. An agent Chrome can be front
  // before its PID is registered, so it may land here briefly; skip it later.
  let recent = [];
  while ($.kill(parent, 0) === 0) {
    const front = $.NSWorkspace.sharedWorkspace.frontmostApplication;
    if (front && !front.isNil()) {
      const txt = $.NSString.stringWithContentsOfFileEncodingError(reg, 4, null);
      const agents = txt.isNil() ? [] : ObjC.unwrap(txt).split(/\s+/).filter(Boolean).map(Number);
      const pid = front.processIdentifier;
      const bundle = ObjC.unwrap(front.bundleIdentifier) || '';
      // Chrome for Testing is only ever an agent browser, and counts before its
      // PID is registered (uc reports it ~4 s after launch).
      if ((agents.indexOf(pid) >= 0 && /chrome/i.test(bundle)) || bundle === 'com.google.chrome.for.testing') {
        const back = recent.find(a => !a.terminated && agents.indexOf(a.processIdentifier) < 0);
        if (back) back.activateWithOptions(0);
      } else if (!recent.length || recent[0].processIdentifier !== pid) {
        if (!recent.length) console.log('ready');  // window_args waits for this
        recent = [front, ...recent.filter(a => a.processIdentifier !== pid)].slice(0, 5);
      }
    }
    // Spin the run loop (a plain sleep freezes frontmostApplication at its first value).
    $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.02));
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
    """Called by every launch site before Chrome starts."""
    if show_browser:
        return ["--window-position=50,50"]
    if sys.platform == "darwin":
        try:
            _start_guard()  # learn the user's app before Chrome grabs focus
        except Exception:
            pass
        lib = _no_activate_lib()
        if lib:
            # Inherited by chromedriver / uc → Chrome. Only Chrome for Testing
            # loads it (branded Chrome is hardened and ignores DYLD_*); other
            # children never touch NSApplication, so the stubs never run there.
            os.environ["DYLD_INSERT_LIBRARIES"] = lib
    return [OFF_SCREEN, *_NO_THROTTLE]


_NO_ACTIVATE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "noactivate.m")


def _no_activate_lib():
    """Build (once per source version) the dylib that stops Chrome activating itself.

    The guard can only undo a focus steal (10–70 ms each, ~7/min while applying)
    and every one still drops the user's keystrokes or closes their menus.
    None if the Xcode command-line tools are missing — the guard then still works.
    """
    try:
        with open(_NO_ACTIVATE_SRC, "rb") as f:
            tag = hashlib.sha1(f.read()).hexdigest()[:12]
        out = os.path.join(os.path.expanduser("~/.cache/jobagent"), f"noactivate-{tag}-universal.dylib")
        if not os.path.exists(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            tmp = f"{out}.{os.getpid()}"
            # Universal: an inherited DYLD_INSERT_LIBRARIES with a wrong-arch lib
            # aborts the child (seen: uc's x86_64 chromedriver under Rosetta).
            subprocess.run(["xcrun", "clang", "-dynamiclib", "-framework", "AppKit",
                            "-arch", "arm64", "-arch", "x86_64",
                            "-o", tmp, _NO_ACTIVATE_SRC], check=True, capture_output=True, timeout=120)
            os.replace(tmp, out)
        return out
    except Exception:
        return None


def testing_chrome():
    """(browser_path, driver_path) of Chrome for Testing, or None.

    Background agents on macOS use it instead of the user's Chrome: branded
    Chrome is hardened, so the no-activate library can't be loaded into it.
    Same build ContextFill already uses, so no second download.
    """
    if sys.platform != "darwin" or not _no_activate_lib():
        return None
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager
        sm = SeleniumManager()
        out = sm.run([str(sm.get_binary()), "--browser", "chrome",
                      "--browser-version", os.environ.get("CONTEXTFILL_CHROME", "beta")])
        return out["browser_path"], out["driver_path"]
    except Exception:
        return None


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
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        # JXA boots in ~1 s; wait until the guard has seen the user's app, or
        # Chrome's launch steal lands before it knows where to send focus back.
        if select.select([_guard.stderr], [], [], 3)[0]:
            _guard.stderr.readline()


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
