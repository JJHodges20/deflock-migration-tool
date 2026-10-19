"""Service metrics (roadmap 13 and 16): counts and latency summaries, bounded memory, no trip data."""

from __future__ import annotations

import json

from deflockmigration.core.metrics import Metrics, process_memory_mb


def test_metrics_summarise_requests_and_plans_in_bounded_memory():
    ticks = iter([0.0, 100.0])
    metrics = Metrics(clock=lambda: next(ticks, 100.0), max_samples=4)
    for duration_ms, status in [(10, 200), (20, 200), (30, 404), (40, 500), (50, 200)]:
        metrics.observe_request("/api/v1/routes/plan", status, duration_ms)
    metrics.observe_request("/api/v1/health/data", 200, 3)
    metrics.observe_plan(search_status="completed", option_count=2, routing_calls=5, elapsed_s=0.7)
    metrics.observe_plan(search_status="budget_exhausted", option_count=1, routing_calls=8, elapsed_s=2.0)
    metrics.observe_plan_error("NO_DRIVABLE_ROUTE")

    snap = metrics.snapshot()
    plan = snap["requests"]["/api/v1/routes/plan"]
    assert plan["count"] == 5 and plan["rejected_4xx"] == 1 and plan["errors_5xx"] == 1
    assert plan["samples"] == 4  # the reservoir keeps only the newest samples
    assert (plan["p50_ms"], plan["p95_ms"], plan["max_ms"]) == (40.0, 50.0, 50.0)
    assert snap["requests"]["/api/v1/health/data"]["count"] == 1
    plans = snap["plans"]
    assert plans["count"] == 2 and plans["by_search_status"] == {"completed": 1, "budget_exhausted": 1}
    assert plans["options_returned"] == {"1": 1, "2": 1} and plans["routing_calls_total"] == 13
    assert plans["errors_by_code"] == {"NO_DRIVABLE_ROUTE": 1}
    assert plans["elapsed_p50_ms"] == 700.0 and plans["elapsed_p95_ms"] == 2000.0 and plans["elapsed_max_ms"] == 2000.0
    assert snap["uptime_seconds"] == 100.0
    text = json.dumps(snap)
    assert "origin" not in text and "destination" not in text and "shape" not in text


def test_empty_metrics_and_process_memory_never_raise():
    snap = Metrics().snapshot()
    assert snap["requests"] == {} and snap["plans"]["count"] == 0 and snap["plans"]["elapsed_p50_ms"] is None
    memory = process_memory_mb()
    assert memory is None or memory > 0
