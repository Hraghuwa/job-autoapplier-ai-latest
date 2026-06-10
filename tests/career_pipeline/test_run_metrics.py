"""Tests for backend.services.run_metrics — the audit's observability layer.

compute_metrics() is a pure function over run records so the metrics math is
verifiable without a live DB: per-platform success rate, apply volume, latency
percentiles, and login-challenge counts. The /admin/metrics endpoint is a thin
wrapper that feeds it AgentRun rows.
"""
from datetime import datetime, timedelta

from backend.services.run_metrics import compute_metrics


def _run(platform="linkedin", status="completed", applied=5, errors=0,
         skipped=0, started=None, completed=None):
    started = started or datetime(2026, 6, 1, 9, 0, 0)
    return {
        "platform": platform,
        "status": status,
        "applied_count": applied,
        "skipped_count": skipped,
        "error_count": errors,
        "started_at": started,
        "completed_at": completed or (started + timedelta(minutes=10)),
    }


def test_empty_input_returns_empty_platforms():
    m = compute_metrics([])
    assert m["platforms"] == {}
    assert m["totals"]["runs"] == 0
    assert m["totals"]["applied"] == 0


def test_per_platform_success_rate():
    runs = [
        _run(status="completed"),
        _run(status="completed"),
        _run(status="failed", applied=0, errors=1),
        _run(platform="internshala", status="completed", applied=3),
    ]
    m = compute_metrics(runs)
    li = m["platforms"]["linkedin"]
    assert li["runs"] == 3
    assert li["completed"] == 2
    assert li["failed"] == 1
    assert abs(li["run_success_rate"] - 2 / 3) < 1e-9
    assert m["platforms"]["internshala"]["runs"] == 1


def test_apply_success_rate_uses_applied_vs_errors():
    runs = [_run(applied=8, errors=2)]
    m = compute_metrics(runs)
    assert abs(m["platforms"]["linkedin"]["apply_success_rate"] - 0.8) < 1e-9


def test_latency_percentiles():
    base = datetime(2026, 6, 1, 9, 0, 0)
    runs = [
        _run(started=base, completed=base + timedelta(seconds=s))
        for s in (60, 120, 300, 600, 6000)
    ]
    m = compute_metrics(runs)
    lat = m["platforms"]["linkedin"]["latency_sec"]
    assert lat["p50"] == 300
    assert lat["p95"] >= 600  # p95 lands on/near the slowest run
    assert lat["count"] == 5


def test_runs_without_timestamps_are_skipped_in_latency():
    r = _run()
    r["completed_at"] = None
    m = compute_metrics([r])
    assert m["platforms"]["linkedin"]["latency_sec"]["count"] == 0


def test_login_challenge_counts_merged():
    m = compute_metrics([_run()], challenge_counts={"linkedin": 4})
    assert m["platforms"]["linkedin"]["login_challenges"] == 4
    # platform with challenges but no runs still surfaces
    m2 = compute_metrics([], challenge_counts={"naukri": 2})
    assert m2["platforms"]["naukri"]["login_challenges"] == 2


def test_totals_aggregate_across_platforms():
    runs = [
        _run(applied=5),
        _run(platform="internshala", applied=3, skipped=2),
    ]
    m = compute_metrics(runs)
    assert m["totals"]["runs"] == 2
    assert m["totals"]["applied"] == 8
    assert m["totals"]["skipped"] == 2


def test_accepts_objects_with_attributes_not_just_dicts():
    class Row:
        platform = "linkedin"
        status = "completed"
        applied_count = 1
        skipped_count = 0
        error_count = 0
        started_at = datetime(2026, 6, 1, 9, 0)
        completed_at = datetime(2026, 6, 1, 9, 5)
    m = compute_metrics([Row()])
    assert m["platforms"]["linkedin"]["runs"] == 1
