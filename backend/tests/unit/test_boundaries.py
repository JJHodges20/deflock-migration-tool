from __future__ import annotations


def test_service_boundary_contains_public_landmarks(app_config):
    b = app_config.service_boundary
    assert b.contains(39.7530, -105.0002)  # Union Station
    assert b.contains(39.8494, -104.6737)  # DEN terminal, airport annexation
    assert not b.contains(39.7047, -104.9339)  # Glendale enclave
    assert not b.contains(39.6654, -105.2057)  # Red Rocks
    west, south, east, north = b.bbox_wsen
    assert west < -105.0 < east and south < 39.75 < north


def test_envelope_contains_service_boundary(app_config):
    assert app_config.envelope.geometry.contains(app_config.service_boundary.geometry)
    assert app_config.envelope.contains(39.7047, -104.9339)  # Glendale cameras are assessed even though trips cannot start there
