"""Read pages with Obscura (github.com/h4ckf0r0day/obscura) instead of a Chrome tab.

Headless, no focus stealing, no profile. Good for public pages (career-page link discovery).
NOT for LinkedIn (challenge page), ContextFill (no extension support) or anything needing login.
Binary: $OBSCURA_BIN, else `obscura` on PATH, else ~/.local/share/obscura/obscura.
Set OBSCURA=0 to force the Chrome fallback.
"""
import os
import shutil
import subprocess


def _bin():
    for p in (os.environ.get("OBSCURA_BIN"), shutil.which("obscura"),
              os.path.expanduser("~/.local/share/obscura/obscura")):
        if p and os.access(p, os.X_OK):
            return p
    return None


def available():
    return os.environ.get("OBSCURA", "1") != "0" and _bin() is not None


def links(url, timeout=45):
    """Rendered-page hrefs, or None if Obscura is unavailable/failed (caller falls back to Chrome)."""
    if not available():
        return None
    try:
        r = subprocess.run([_bin(), "fetch", url, "--dump", "links"], capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    # one "url<TAB>anchor text" per line
    return [ln.split("\t", 1)[0].strip() for ln in r.stdout.splitlines() if ln.startswith("http")]


if __name__ == "__main__":  # smoke check: python agents/obscura_fetch.py https://jobs.lever.co/palantir
    import sys
    out = links(sys.argv[1])
    assert out, "no links (Obscura missing or page failed)"
    print(len(out), "links; first:", out[0])
