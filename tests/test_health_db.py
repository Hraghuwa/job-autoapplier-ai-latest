"""/health must report DB reachability (so an expired/missing DB is obvious).

Guards the fix for the "Railway plan expired → login looks broken" confusion:
/health stays 200 but now carries a `database` field. Also checks db_ping is a
never-raising bool.
"""
import asyncio

from fastapi.testclient import TestClient

import backend.main as m
from backend.database import db_ping


def test_health_reports_database_field():
    r = TestClient(m.app).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] in ("ok", "unreachable")


def test_health_db_ok_on_local_sqlite():
    # The test suite runs on the SQLite default → DB must be reachable.
    body = TestClient(m.app).get("/health").json()
    assert body["database"] == "ok"


def test_db_ping_returns_bool_and_never_raises():
    out = asyncio.get_event_loop().run_until_complete(db_ping())
    assert isinstance(out, bool)
