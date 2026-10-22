"""Chrome window flags for the "Show browser" toggle.

Background (default): a real, non-headless Chrome parked off-screen so it never
covers the user's work. Headless is avoided on purpose — it trips LinkedIn /
Naukri bot checks. The anti-throttling flags keep a hidden window running at
full speed; progress is visible in the run's live logs.
"""

OFF_SCREEN = "--window-position=-32000,-32000"

_NO_THROTTLE = [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]


def window_args(show_browser: bool) -> list:
    if show_browser:
        return ["--window-position=50,50"]
    return [OFF_SCREEN, *_NO_THROTTLE]


def show_browser(config: dict) -> bool:
    return bool((config or {}).get("show_browser", False))


def bring_on_screen(driver) -> None:
    """Pull a background window on-screen when a human must act (CAPTCHA/2FA)."""
    try:
        driver.set_window_position(50, 50)
        print("  👀 Browser window brought on-screen — action needed.")
    except Exception:
        pass


def park_off_screen(driver, show_browser: bool) -> None:
    """Move a background window fully off-screen right after launch.

    macOS clamps the --window-position launch flag and leaves a sliver of the
    window visible; a post-launch move lands fully off-screen.
    """
    if show_browser:
        return
    try:
        driver.set_window_position(-32000, -32000)
    except Exception:
        pass
