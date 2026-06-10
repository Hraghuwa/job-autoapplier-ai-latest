"""Observability layer — the audit's meta-gap (§6c proposal, now implemented).

The system optimised things it could not measure: no success rates, no latency,
no per-platform health. This module computes those from AgentRun rows. It is a
PURE function over plain records (dicts or ORM rows) so the math is unit-tested
without a database; routers/admin.py exposes it at GET /admin/metrics.

Cost/token metrics are intentionally NOT here yet — llm_router doesn't capture
usage. That is the documented next step (write usage rows to ai_requests).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _get(rec: Any, key: str, default=None):
    """Read a field from a dict OR an object (ORM row) uniformly."""
    if isinstance(rec, dict):
        return rec.get(key, default)
    return getattr(rec, key, default)


def _percentile(sorted_vals: List[float], pct: float) -> float:
    """Nearest-rank percentile; assumes sorted input, non-empty."""
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1,
                   round(pct / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def compute_metrics(
    runs: Iterable[Any],
    challenge_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Aggregate AgentRun records into per-platform + total metrics.

    runs: AgentRun rows or dicts with platform/status/applied_count/
          skipped_count/error_count/started_at/completed_at.
    challenge_counts: optional {platform: n} of login_challenge log events.

    Returns:
      {
        "platforms": {platform: {runs, completed, failed, applied, skipped,
                                 errors, run_success_rate, apply_success_rate,
                                 latency_sec: {p50, p95, count},
                                 login_challenges}},
        "totals": {runs, applied, skipped, errors},
      }
    """
    challenge_counts = challenge_counts or {}
    per: Dict[str, Dict[str, Any]] = {}
    latencies: Dict[str, List[float]] = {}
    totals = {"runs": 0, "applied": 0, "skipped": 0, "errors": 0}

    def _bucket(platform: str) -> Dict[str, Any]:
        return per.setdefault(platform, {
            "runs": 0, "completed": 0, "failed": 0,
            "applied": 0, "skipped": 0, "errors": 0,
            "run_success_rate": 0.0, "apply_success_rate": 0.0,
            "latency_sec": {"p50": 0.0, "p95": 0.0, "count": 0},
            "login_challenges": 0,
        })

    for r in runs:
        platform = str(_get(r, "platform") or "unknown")
        b = _bucket(platform)
        status = str(_get(r, "status") or "")
        # Enum values like RunStatus.completed stringify as "RunStatus.completed"
        status = status.split(".")[-1].lower()

        b["runs"] += 1
        totals["runs"] += 1
        if status == "completed":
            b["completed"] += 1
        elif status == "failed":
            b["failed"] += 1

        applied = int(_get(r, "applied_count") or 0)
        skipped = int(_get(r, "skipped_count") or 0)
        errors = int(_get(r, "error_count") or 0)
        b["applied"] += applied
        b["skipped"] += skipped
        b["errors"] += errors
        totals["applied"] += applied
        totals["skipped"] += skipped
        totals["errors"] += errors

        started = _get(r, "started_at")
        completed = _get(r, "completed_at")
        if started and completed:
            try:
                dur = (completed - started).total_seconds()
                if dur >= 0:
                    latencies.setdefault(platform, []).append(dur)
            except Exception:
                pass

    # Platforms that have challenge events but no runs still surface.
    for platform in challenge_counts:
        _bucket(platform)

    for platform, b in per.items():
        terminal = b["completed"] + b["failed"]
        b["run_success_rate"] = (b["completed"] / terminal) if terminal else 0.0
        attempts = b["applied"] + b["errors"]
        b["apply_success_rate"] = (b["applied"] / attempts) if attempts else 0.0
        lats = sorted(latencies.get(platform, []))
        b["latency_sec"] = {
            "p50": _percentile(lats, 50),
            "p95": _percentile(lats, 95),
            "count": len(lats),
        }
        b["login_challenges"] = int(challenge_counts.get(platform, 0))

    return {"platforms": per, "totals": totals}
