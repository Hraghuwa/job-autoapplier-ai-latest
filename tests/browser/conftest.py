"""Headless-Chrome harness for real selector/fill tests.

These exercise the actual applier functions against a real DOM loaded from local
HTML fixtures — the only way to catch selector bugs (label leakage, wrong-field
fills) that pure unit tests miss. The `chrome_driver` fixture SKIPS (not fails)
when Chrome/driver can't launch, so CI without a browser stays green while local
runs get real verification.
"""
import os
import sys

import pytest

# Make the agents/ appliers importable, and also repo root for imports like submit_gate/backend.
agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents"))
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, agents_dir)
sys.path.insert(1, root_dir)


def _build_driver():
    import glob
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--allow-file-access-from-files")
    opts.add_argument("--disable-web-security")
    wdm = ChromeDriverManager().install()
    d = os.path.dirname(wdm)
    binary = next((p for p in glob.glob(os.path.join(d, "chromedriver*"))
                   if os.path.isfile(p) and "NOTICES" not in p), wdm)
    os.chmod(binary, 0o755)
    return webdriver.Chrome(service=Service(binary), options=opts)


def _chrome_binary_present():
    import shutil
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium", "/usr/bin/chromium-browser",
        shutil.which("google-chrome"), shutil.which("chromium"),
        shutil.which("chrome"),
    ]
    return any(c and os.path.exists(c) for c in candidates)


@pytest.fixture(scope="session")
def chrome_driver():
    # Fast skip when there's no browser at all (e.g. CI without Chrome) — avoids
    # a slow webdriver-manager download that would only fail on launch anyway.
    if not _chrome_binary_present():
        pytest.skip("no Chrome binary on this host — skipping live-DOM tests")
    try:
        driver = _build_driver()
    except Exception as e:
        pytest.skip(f"headless Chrome unavailable: {type(e).__name__}: {e}")
        return
    yield driver
    try:
        driver.quit()
    except Exception:
        pass


@pytest.fixture(scope="session")
def http_server():
    import socket
    import threading
    import http.server
    from functools import partial

    # Find a free port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()

    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")

    class SilentSimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    handler = partial(SilentSimpleHTTPRequestHandler, directory=fixtures_dir)
    server = http.server.HTTPServer(('127.0.0.1', port), handler)
    
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    yield f"http://127.0.0.1:{port}"
    
    server.shutdown()
    server.server_close()


@pytest.fixture()
def load_fixture(chrome_driver, http_server):
    """Return a loader: load_fixture('name.html') → driver on that page."""
    def _load(name):
        chrome_driver.get(f"{http_server}/{name}")
        return chrome_driver

    return _load

