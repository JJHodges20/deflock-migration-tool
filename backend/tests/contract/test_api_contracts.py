"""API contract tests with fake providers. No network, no database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from deflockmigration.api.app import create_app
from deflockmigration.geocoding.provider import NullGeocoder
from tests.conftest import FakeRoutingProvider

UNION_STATION = {"lat": 39.7530, "lon": -105.0002}
ZOO = {"lat": 39.7503, "lon": -104.9500}
GLENDALE = {"lat": 39.7047, "lon": -104.9339}


def test_region_contract(client: TestClient):
    resp = client.get("/api/v1/region")
    assert resp.status_code == 200 and resp.headers["X-Request-ID"]
    body = resp.json()
    assert body["region_id"] == "denver" and body["service_boundary"]["id"] == "denver-service-v1"
    assert body["service_boundary"]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert body["camera_data_envelope"]["buffer_m"] == 20000
    assert body["capabilities"]["geocoder_configured"] is False and body["capabilities"]["map_pins"] is True
    assert set(body["profiles"]) == {"standard", "balanced", "fewest_mapped"}
    assert body["camera_scopes"] == ["all_alpr", "flock_only"]
    assert "surveillance-free" in body["disclaimer"] and any("OpenStreetMap" in a for a in body["attributions"])


def test_health_endpoints(client: TestClient):
    assert client.get("/api/v1/health/live").json()["status"] == "ok"
    data = client.get("/api/v1/health/data").json()
    assert data["database"] == {"available": False, "message": "database not configured"}
    assert data["router"]["available"] is True and data["router"]["graph_id"].startswith("colorado-geofabrik")
    assert data["geocoder"]["configured"] is False
    assert data["snapshot"] is None and data["staleness"] == {}


def test_plan_returns_standard_route_without_camera_claims(client: TestClient, fake_routing: FakeRoutingProvider):
    resp = client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["search_status"] == "completed" and body["assessment_coverage_status"] == "not_assessed"
    assert len(body["options"]) == 1
    option = body["options"][0]
    assert option["profiles"] == ["standard"]
    assert option["matched_camera_record_count"] is None and option["uncertain_nearby_camera_count"] is None
    assert option["camera_snapshot_id"] is None
    assert option["geometry"]["type"] == "LineString" and len(option["geometry"]["coordinates"]) > 50
    assert option["maneuvers"][0]["type_name"].startswith("start") and option["maneuvers"][-1]["type_name"].startswith("destination")
    assert all(m["instruction"] for m in option["maneuvers"])
    assert option["road_graph_version"].startswith("colorado-geofabrik")
    # Decision 0001 D6: the fixture's primary is slower than its alternates, so Standard is an alternate.
    assert option["engine_candidate"].startswith("alternate")
    assert any("fastest baseline candidate" in w for w in body["warnings"])
    assert fake_routing.calls[0]["alternates"] == 2
    assert "surveillance-free" in body["disclaimer"]


def test_plan_outside_service_area(client: TestClient):
    resp = client.post("/api/v1/routes/plan", json={"origin": GLENDALE, "destination": ZOO})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "OUTSIDE_SERVICE_AREA" and body["error"]["details"]["outside"] == ["origin"]
    assert body["request_id"]


def test_plan_validation_errors(client: TestClient):
    resp = client.post("/api/v1/routes/plan", json={"origin": {"lat": 100, "lon": 0}, "destination": ZOO})
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "origin.lat" in resp.json()["error"]["details"]["fields"]
    resp = client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO, "surprise": 1})
    assert resp.status_code == 400
    resp = client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO, "region_id": "boulder"})
    assert resp.status_code == 400 and resp.json()["error"]["details"]["region_id"] == "boulder"


def test_router_unavailable_and_no_route(settings, app_config, valhalla_fixture_payload):
    for mode, code, status in (("unavailable", "ROUTER_UNAVAILABLE", 503), ("no_route", "NO_DRIVABLE_ROUTE", 422)):
        app = create_app(settings, config=app_config, routing=FakeRoutingProvider(valhalla_fixture_payload, mode=mode), geocoder=NullGeocoder())
        resp = TestClient(app).post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO})
        assert resp.status_code == status and resp.json()["error"]["code"] == code


def test_geocode_coordinates_bypass_provider(client: TestClient):
    resp = client.post("/api/v1/geocode", json={"query": "39.7530, -105.0002"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_kind"] == "coordinates" and body["candidates"][0]["inside_service_boundary"] is True
    resp = client.post("/api/v1/geocode", json={"query": "39.7047, -104.9339"})
    assert resp.json()["candidates"][0]["inside_service_boundary"] is False


def test_geocode_not_configured(client: TestClient):
    resp = client.post("/api/v1/geocode", json={"query": "Union Station"})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "GEOCODER_NOT_CONFIGURED"
    assert client.post("/api/v1/geocode", json={"query": ""}).status_code == 400
    resp = client.post("/api/v1/geocode/reverse", json={"lat": 39.753, "lon": -105.0002})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "GEOCODER_NOT_CONFIGURED"
    assert client.post("/api/v1/geocode/reverse", json={"lat": 95, "lon": 0}).status_code == 400


def test_geocode_swapped_coordinates_are_explained(client: TestClient):
    body = client.post("/api/v1/geocode", json={"query": "-105.0002, 39.7530"}).json()
    candidate = body["candidates"][0]
    assert candidate["lat"] == 39.753 and candidate["lon"] == -105.0002 and candidate["inside_service_boundary"] is True
    assert "swapped" in candidate["note"]


def test_plan_reports_snapping_and_rejects_identical_points(client: TestClient):
    body = client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO}).json()
    option = body["options"][0]
    assert option["origin_snap_distance_meters"] >= 0 and option["destination_snap_distance_meters"] >= 0
    resp = client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": UNION_STATION})
    assert resp.status_code == 400 and "same place" in resp.json()["error"]["message"]


def test_cameras_without_database_and_bad_bbox(client: TestClient):
    resp = client.get("/api/v1/cameras", params={"bbox": "-105.0,39.7,-104.9,39.8"})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "CAMERA_DATA_UNAVAILABLE"
    assert client.get("/api/v1/cameras", params={"bbox": "1,2,3"}).status_code == 400
    assert client.get("/api/v1/cameras", params={"bbox": "-105,39,-103,41"}).status_code == 400
    assert client.get("/api/v1/cameras", params={"bbox": "-104.9,39.8,-105.0,39.7"}).status_code == 400


def test_plan_without_database_is_not_assessed_with_null_counts(client: TestClient):
    body = client.post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO}).json()
    option = body["options"][0]
    assert option["assessment"] is None and option["matched_camera_record_count"] is None
    assert body["assessment_coverage_status"] == "not_assessed"


def test_plan_maps_a_complete_assessment(settings, app_config, valhalla_fixture_payload):
    from deflockmigration.domain.assessment import AssessmentResult, Association, Encounter, EncounterStatus, SensitivityCount

    def fake_assessor(route, scope, snapshot_id):
        association = Association("valhalla_locate_nearest_way", 50.0, "g@2026", 1, ["Main Street"], 4.0, 1, ["Main Street"], 4.0, 1, True, False, False, "nearest road traversed")
        encounter = Encounter("osm:node:1", 39.75, -104.99, EncounterStatus.ASSOCIATED, 4.0, 0.5, 3200.0, 1, "osm:node:1", "flock_safety", True, "mapped", "90", False, "mapped direction 90°", True, "https://www.openstreetmap.org/node/1", association, "nearest road traversed")
        uncertain = Encounter("osm:node:2", 39.76, -104.98, EncounterStatus.NEARBY_UNRESOLVED, 30.0, 0.7, 4500.0, 1, "osm:node:2", None, False, "mapped", None, False, None, True, "https://www.openstreetmap.org/node/2", None, "parallel road")
        return AssessmentResult("complete", "assess-1.0", 50.0, scope.value, "snap-1", "g@2026", 1, 1, 1.0, [encounter, uncertain], [SensitivityCount(25, 1), SensitivityCount(50, 2), SensitivityCount(100, 2)], [])

    app = create_app(settings, config=app_config, routing=FakeRoutingProvider(valhalla_fixture_payload), geocoder=NullGeocoder(), assessor=fake_assessor)
    body = TestClient(app).post("/api/v1/routes/plan", json={"origin": UNION_STATION, "destination": ZOO, "camera_scope": "flock_only"}).json()
    option = body["options"][0]
    assert option["matched_camera_record_count"] == 1 and option["uncertain_nearby_camera_count"] == 1
    assert option["assessment_coverage_status"] == "complete" and body["assessment_coverage_status"] == "complete"
    assert option["counting_method_version"] == "assess-1.0" and option["road_graph_version"] == "g@2026"
    assessment = option["assessment"]
    assert assessment["scope"] == "flock_only" and [s["records_within"] for s in assessment["sensitivity"]] == [1, 2, 2]
    assert assessment["encounters"][0]["status"] == "associated" and assessment["encounters"][0]["association"]["same_road"] is True
    assert assessment["encounters"][1]["status"] == "nearby_unresolved" and assessment["encounters"][1]["association"] is None
    assert "not observed recordings" in assessment["meaning"]


def test_camera_record_endpoint_contract(client: TestClient):
    resp = client.get("/api/v1/cameras/record", params={"source_key": "not-a-key"})
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "VALIDATION_ERROR"
    resp = client.get("/api/v1/cameras/record", params={"source_key": "osm:node:123"})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "CAMERA_DATA_UNAVAILABLE"


def test_health_data_inventory_block(client: TestClient):
    data = client.get("/api/v1/health/data").json()
    inventory = data["inventory"]
    assert inventory["retain_missing_hours"] == 72 and inventory["unresolved_disappearance"] == "retain_as_uncertain"
    assert inventory["keep_superseded_snapshots"] == 30 and inventory["pending_review"] == []
    assert data["recent_syncs"] == []


def test_oversized_body_is_rejected(client: TestClient):
    resp = client.post("/api/v1/routes/plan", content=b"{}", headers={"Content-Type": "application/json", "Content-Length": str(70 * 1024)})
    assert resp.status_code == 413
