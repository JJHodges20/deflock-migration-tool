"""Service boundary and envelope checks for the configured region (Colorado since M9) and for the retained Denver
pilot configuration. Point-in-polygon only; nothing here measures meters in degrees."""

from __future__ import annotations

from deflockmigration.core.config_loader import load_app_config
from deflockmigration.core.settings import Settings

UNION_STATION = (39.7530, -105.0002)
DEN_TERMINAL = (39.8494, -104.6737)
GLENDALE = (39.7047, -104.9339)
RED_ROCKS = (39.6654, -105.2057)
GRAND_JUNCTION = (39.0639, -108.5506)
COLORADO_SPRINGS = (38.8339, -104.8214)
DURANGO = (37.2753, -107.8801)
CHEYENNE_WY = (41.1400, -104.8202)
SANTA_FE_NM = (35.6870, -105.9378)
GREEN_RIVER_UT = (38.9955, -110.1596)


def test_colorado_service_boundary_contains_the_state_and_not_its_neighbours(app_config):
    b = app_config.service_boundary
    assert b.boundary_id == "colorado-service-v1"
    for point in (UNION_STATION, DEN_TERMINAL, GLENDALE, RED_ROCKS, GRAND_JUNCTION, COLORADO_SPRINGS, DURANGO):
        assert b.contains(*point), point
    for point in (CHEYENNE_WY, SANTA_FE_NM, GREEN_RIVER_UT):
        assert not b.contains(*point), point
    west, south, east, north = b.bbox_wsen
    assert -109.1 < west < -109.0 and 36.9 < south < 37.1 and -102.1 < east < -102.0 and 40.9 < north < 41.1


def test_colorado_envelope_contains_the_boundary_and_stays_inside_the_graph(app_config):
    env = app_config.envelope
    assert env.boundary_id == "colorado-envelope-v1-20km"
    assert env.geometry.contains(app_config.service_boundary.geometry)
    assert env.contains(*CHEYENNE_WY)  # within 20 km of the state line: cameras there are assessed, trips cannot start there
    west, south, east, north = env.bbox_wsen
    assert west >= -109.5 and east <= -101.5 and south >= 36.75 and north <= 41.5  # the routing graph's tileset extent


def test_denver_pilot_configuration_still_loads(project_root):
    settings = Settings(app_env="test", project_root=project_root, database_url=None, geocoder_url=None, region_config="configs/regions/denver.yaml")
    cfg = load_app_config(settings)
    b = cfg.service_boundary
    assert cfg.region.region_id == "denver" and b.boundary_id == "denver-service-v1"
    assert b.contains(*UNION_STATION) and b.contains(*DEN_TERMINAL)
    assert not b.contains(*GLENDALE) and not b.contains(*RED_ROCKS)  # the enclave and the foothills are outside the Denver pilot area
    assert cfg.envelope.geometry.contains(b.geometry) and cfg.envelope.contains(*GLENDALE)
