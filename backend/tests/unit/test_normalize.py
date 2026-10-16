from __future__ import annotations

from deflockmigration.domain.cameras import LifecycleState
from deflockmigration.ingestion.normalize import normalize_element, normalize_elements, normalize_manufacturer, parse_direction


def test_fixture_sample_buckets(overpass_fixture_payload):
    records = normalize_elements(overpass_fixture_payload["elements"])
    assert len(records) == len(overpass_fixture_payload["elements"])
    by_key = {r.source_key: r for r in records}
    buckets = {e["_fixture_bucket"] for e in overpass_fixture_payload["elements"]}
    assert {"flock_direction", "manufacturer_absent", "other_manufacturer"} <= buckets
    for element in overpass_fixture_payload["elements"]:
        record = by_key[f"osm:{element['type']}:{element['id']}"]
        bucket = element["_fixture_bucket"]
        tags = element.get("tags", {})
        if bucket.startswith("flock"):
            assert record.is_flock and record.manufacturer_normalized == "flock_safety"
        if bucket == "manufacturer_absent":
            assert record.manufacturer_normalized is None and not record.is_flock
        if bucket == "other_manufacturer":
            assert not record.is_flock and record.manufacturer_normalized not in (None, "flock_safety")
        if bucket == "direction_conflict":
            assert record.direction_conflict and "disagree" in " ".join(record.parse_warnings)
        if "alpr" in tags.get("surveillance:type", "").lower():
            assert record.is_alpr
        assert record.raw_tags == {k: str(v) for k, v in tags.items()}
        assert record.source_version == element["version"]
        assert record.source_timestamp is not None


def test_gunshot_detector_is_not_alpr():
    element = {"type": "node", "id": 1, "lat": 39.7, "lon": -104.9, "tags": {"man_made": "surveillance", "surveillance:type": "gunshot_detector", "manufacturer": "Flock Safety"}}
    record = normalize_element(element)
    assert record is not None and not record.is_alpr and record.is_flock
    assert any("excluded from encounter counts" in w for w in record.parse_warnings)


def test_lifecycle_prefix_marks_removed_but_keeps_alpr_typing():
    element = {"type": "node", "id": 2, "lat": 39.7, "lon": -104.9, "tags": {"removed:man_made": "surveillance", "removed:surveillance:type": "ALPR"}}
    record = normalize_element(element)
    assert record is not None and record.is_alpr and record.lifecycle_state is LifecycleState.REMOVED
    assert record.lifecycle_evidence == "removed:surveillance:type=ALPR"


def test_aliases_count_as_alpr():
    for tags in ({"surveillance:type": "ANPR"}, {"camera:type": "ALPR"}, {"surveillance": "license_plate_scanner"}):
        record = normalize_element({"type": "node", "id": 3, "lat": 39.7, "lon": -104.9, "tags": tags})
        assert record is not None and record.is_alpr, tags


def test_brand_flock_without_manufacturer_is_not_flock_scope():
    record = normalize_element({"type": "node", "id": 4, "lat": 39.7, "lon": -104.9, "tags": {"surveillance:type": "ALPR", "brand": "Flock Safety"}})
    assert record is not None and record.is_alpr and not record.is_flock and record.manufacturer_normalized is None


def test_direction_parsing():
    assert parse_direction("135") == (135.0, None)
    assert parse_direction("360") == (0.0, None)
    assert parse_direction("NE") == (45.0, None)
    assert parse_direction("315-45")[0] is None and "range" in parse_direction("315-45")[1]
    assert parse_direction("90;270")[0] is None and "multi" in parse_direction("90;270")[1]
    assert parse_direction(None) == (None, None)


def test_manufacturer_normalization():
    assert normalize_manufacturer("Flock Safety") == "flock_safety"
    assert normalize_manufacturer("flock") == "flock_safety"
    assert normalize_manufacturer("Motorola Solutions") == "motorola_solutions"
    assert normalize_manufacturer("Axis Communications") == "axis_communications"
    assert normalize_manufacturer("") is None and normalize_manufacturer(None) is None


def test_non_point_elements_use_representative_point_and_duplicates_are_dropped():
    way = {"type": "way", "id": 10, "center": {"lat": 39.70, "lon": -104.90}, "tags": {"surveillance:type": "ALPR"}}
    records = normalize_elements([way, way, {"type": "relation", "id": 11, "tags": {"surveillance:type": "ALPR"}}])
    assert len(records) == 1
    assert records[0].geometry_quality == "representative_point"
    assert records[0].source_key == "osm:way:10"
