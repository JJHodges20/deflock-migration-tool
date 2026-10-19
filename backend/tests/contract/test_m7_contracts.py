"""M7 contracts: metrics without trip data, scheduler and provider policy in Data Health, diff history."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

UNION_STATION = {"lat": 39.7530, "lon": -105.0002}
ZOO = {"lat": 39.7503, "lon": -104.9500}


def test_metrics_endpoint_counts_requests_without_trip_data(client: TestClient):
    client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO})
    client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": UNION_STATION})  # rejected: same place
    body = client.get("/api/v1/health/metrics").json()
    plan = body["requests"]["/api/v1/routes/plan"]
    assert plan["count"] == 2 and plan["rejected_4xx"] == 1 and plan["p50_ms"] is not None
    assert body["plans"]["count"] == 1 and body["plans"]["errors_by_code"] == {"VALIDATION_ERROR": 1}
    assert body["plans"]["by_search_status"] == {"completed": 1} and body["plans"]["routing_calls_total"] == 1
    assert body["storage"]["available"] is False and body["process"]["version"]
    text = json.dumps(body)
    for forbidden in ("39.75", "-105.0", "origin", "destination", "shape", "locations"):
        assert forbidden not in text, forbidden


def test_data_health_reports_scheduler_and_provider_policy_without_database(client: TestClient):
    body = client.get("/api/v1/health/data").json()
    scheduler = body["scheduler"]
    assert scheduler["overdue"] is True and scheduler["next_due_at"] is None and scheduler["runs_only_while_stack_is_up"] is True
    assert scheduler["interval_hours"] == 6 and scheduler["manual_refresh_cooldown_minutes"] == 30
    policy = body["provider_policy"]
    assert policy["one_request_at_a_time"] is True and policy["no_endpoint_rotation"] is True
    assert policy["pause_after_rate_limit_seconds"] >= 30 and policy["max_attempts"] >= 1 and "never derived from a trip" in policy["query"]
    assert body["router"]["rebuild_cadence"]


def test_camera_diff_history_without_database_is_unavailable_not_empty(client: TestClient):
    resp = client.get("/api/v1/cameras/diffs")
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "CAMERA_DATA_UNAVAILABLE"
