"""Background vs visible agent browser (the "Show browser" toggle).

Background = a real (non-headless) Chrome parked off-screen, so it never covers
the user's work but still passes bot checks, and isn't throttled while hidden.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents")))

from browser_window import window_args, bring_on_screen, park_off_screen


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
    def __init__(self, fail=False):
        self.pos, self.fail = None, fail

    def set_window_position(self, x, y):
        if self.fail:
            raise RuntimeError("window gone")
        self.pos = (x, y)


def test_bring_on_screen_moves_hidden_window_for_captcha():
    d = _FakeDriver()
    bring_on_screen(d)
    assert d.pos == (50, 50)


def test_bring_on_screen_never_raises():
    bring_on_screen(_FakeDriver(fail=True))
    bring_on_screen(None)


def test_park_off_screen_moves_window_after_launch():
    # macOS clamps the --window-position launch flag (a sliver stays visible);
    # a post-launch move goes fully off-screen.
    d = _FakeDriver()
    park_off_screen(d, show_browser=False)
    assert d.pos == (-32000, -32000)


def test_park_off_screen_noop_when_visible():
    d = _FakeDriver()
    park_off_screen(d, show_browser=True)
    assert d.pos is None
    park_off_screen(_FakeDriver(fail=True), show_browser=False)  # never raises
