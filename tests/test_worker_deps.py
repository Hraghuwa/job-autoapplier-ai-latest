"""Guards the 'No module named selenium' worker outage.

- agent_supervisor.healthcheck must report selenium importability + chrome binary
  so a misconfigured worker is diagnosable (not just a buried run error).
- orchestrator._resolve_chrome_paths must honour CHROME_BIN/CHROMEDRIVER_PATH so
  the container uses the distro Chromium instead of a runtime download.
"""
import importlib.util
import os
import sys

_AGENTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents"))
if _AGENTS not in sys.path:
    sys.path.insert(0, _AGENTS)


def _agents_orchestrator():
    """Load agents/orchestrator.py explicitly — a bare `import orchestrator` is
    ambiguous (there's also a root legacy orchestrator.py). The worker subprocess
    loads the agents one (agents on sys.path first)."""
    spec = importlib.util.spec_from_file_location(
        "agents_orchestrator_test", os.path.join(_AGENTS, "orchestrator.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_healthcheck_reports_selenium_and_chrome_keys():
    from backend.services.agent_supervisor import healthcheck
    h = healthcheck()
    assert "selenium" in h and isinstance(h["selenium"], bool)
    assert "chrome_binary" in h
    assert h["selenium"] is True  # selenium is in requirements now → importable


def test_resolve_chrome_paths_honours_env(tmp_path, monkeypatch):
    orch = _agents_orchestrator()
    fake_bin = tmp_path / "chromium"; fake_bin.write_text("x")
    fake_drv = tmp_path / "chromedriver"; fake_drv.write_text("x")
    monkeypatch.setenv("CHROME_BIN", str(fake_bin))
    monkeypatch.setenv("CHROMEDRIVER_PATH", str(fake_drv))
    chrome, driver = orch._resolve_chrome_paths()
    assert chrome == str(fake_bin) and driver == str(fake_drv)


def test_resolve_chrome_paths_ignores_missing(monkeypatch):
    orch = _agents_orchestrator()
    monkeypatch.setenv("CHROME_BIN", "/nope/chromium")
    monkeypatch.delenv("CHROMEDRIVER_PATH", raising=False)
    chrome, driver = orch._resolve_chrome_paths()
    assert chrome is None and driver is None  # nonexistent path → fall back
