"""Pure tests for DATABASE_URL handling — de-risks the Railway→Neon migration.

Covers driver coercion and the asyncpg sslmode trap (Neon URLs carry
?sslmode=require, which asyncpg rejects unless translated to ssl=)."""
from backend.database import _coerce_async_url, _split_sslmode


def test_coerce_bare_postgres():
    assert _coerce_async_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"

def test_coerce_postgresql():
    assert _coerce_async_url("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"

def test_coerce_idempotent_for_asyncpg():
    u = "postgresql+asyncpg://u:p@h/db"
    assert _coerce_async_url(u) == u

def test_coerce_leaves_sqlite_alone():
    u = "sqlite+aiosqlite:////tmp/x.db"
    assert _coerce_async_url(u) == u

def test_neon_sslmode_is_stripped_from_url():
    url = _coerce_async_url("postgresql://u:p@ep-x.neon.tech/db?sslmode=require")
    clean, ssl = _split_sslmode(url)
    assert "sslmode" not in clean       # asyncpg would choke on it
    assert ssl == "require"

def test_sslmode_disable_maps_to_no_url_param():
    clean, ssl = _split_sslmode("postgresql+asyncpg://u:p@h/db?sslmode=disable")
    assert "sslmode" not in clean and ssl == "disable"

def test_no_sslmode_unchanged():
    u = "postgresql+asyncpg://u:p@h/db"
    assert _split_sslmode(u) == (u, None)

def test_sslmode_only_touched_for_asyncpg():
    # A non-asyncpg url is returned untouched (no accidental query surgery).
    u = "sqlite+aiosqlite:////tmp/x.db"
    assert _split_sslmode(u) == (u, None)

def test_other_query_params_preserved():
    clean, ssl = _split_sslmode(
        "postgresql+asyncpg://u:p@h/db?sslmode=require&application_name=ja")
    assert "application_name=ja" in clean and "sslmode" not in clean and ssl == "require"
