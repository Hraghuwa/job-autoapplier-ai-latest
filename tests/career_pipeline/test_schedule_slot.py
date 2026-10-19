import builtins
from datetime import datetime

from backend.workers.agent_tasks import _last_cron_slot

NOW = datetime(2026, 10, 19, 9, 20)


def _no_croniter(monkeypatch):
    real = builtins.__import__
    def fake(name, *a, **k):
        if name == "croniter":
            raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)


def test_slot_with_croniter():
    assert _last_cron_slot("0 9 * * *", NOW) == datetime(2026, 10, 19, 9, 0)
    assert _last_cron_slot("30 9 * * *", NOW) == datetime(2026, 10, 18, 9, 30)
    assert _last_cron_slot("garbage", NOW) is None


def test_slot_fallback_daily_only(monkeypatch):
    _no_croniter(monkeypatch)
    assert _last_cron_slot("0 9 * * *", NOW) == datetime(2026, 10, 19, 9, 0)
    assert _last_cron_slot("30 9 * * *", NOW) == datetime(2026, 10, 18, 9, 30)
    assert _last_cron_slot("0 9 * * 1", NOW) is None
    assert _last_cron_slot("0 * * * *", NOW) is None
