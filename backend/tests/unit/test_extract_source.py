"""M10: camera records from a regional extract and the replication-based source adapter, without any network.

The extract is a tiny PBF written with pyosmium; the replication server is a fake that records the requests it
receives. The pyosmium extension is installed in the backend image; host runs without it skip this module.
"""

from __future__ import annotations

import datetime as dt
import types
from collections import namedtuple
from pathlib import Path

import pytest

from deflockmigration.core.config_loader import CameraSourceConfig, ConfigError, load_app_config
from deflockmigration.core.settings import Settings
from deflockmigration.data_sources.extract_elements import FILTER_KEYS, matches_camera_filter
from deflockmigration.ingestion.normalize import normalize_elements

osmium = pytest.importorskip("osmium")

from osmium.osm import mutable  # noqa: E402

from deflockmigration.data_sources.osm_extract import ExtractSource  # noqa: E402
from deflockmigration.data_sources.overpass import OverpassSource  # noqa: E402
from deflockmigration.data_sources.extract_elements import extract_camera_elements  # noqa: E402
from deflockmigration.workers.camera_sync import build_source  # noqa: E402

REPLICATION_URL = "https://replication.test/colorado-updates"
State = namedtuple("State", "sequence timestamp")
TS = dt.datetime(2026, 10, 18, 20, 25, 6, tzinfo=dt.UTC)
NOW = dt.datetime(2026, 10, 20, 1, 0, tzinfo=dt.UTC)
CAMERA = {"man_made": "surveillance", "surveillance:type": "ALPR", "manufacturer": "Flock Safety", "camera:direction": "90"}
DENVER = (-104.9903, 39.7392)  # lon, lat
PUEBLO = (-104.6091, 38.2544)
CHEYENNE = (-104.8202, 41.1400)


def write_pbf(path: Path, *, sequence: int | None, timestamp: dt.datetime = TS, nodes=(), ways=(), relations=()) -> Path:
    """A minimal extract with Osmosis replication headers, written in the order pyosmium requires."""
    header = osmium.io.Header()
    if sequence is not None:
        header.set("osmosis_replication_base_url", REPLICATION_URL)
        header.set("osmosis_replication_sequence_number", str(sequence))
    header.set("osmosis_replication_timestamp", timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with osmium.SimpleWriter(str(path), header=header, overwrite=True) as writer:
        for node_id, lon, lat, tags in sorted(nodes):
            writer.add_node(mutable.Node(id=node_id, version=2, visible=True, changeset=1, timestamp=timestamp, uid=0, user="", tags=tags, location=(lon, lat)))
        for way_id, refs, tags in sorted(ways):
            writer.add_way(mutable.Way(id=way_id, version=1, visible=True, changeset=1, timestamp=timestamp, uid=0, user="", tags=tags, nodes=refs))
        for relation_id, members, tags in sorted(relations):
            writer.add_relation(mutable.Relation(id=relation_id, version=1, visible=True, changeset=1, timestamp=timestamp, uid=0, user="", tags=tags, members=members))
    return path


class FakeServer:
    """What the adapter asks a replication server, answered from a table and recorded."""

    def __init__(self, states: dict, apply=None):
        self.states = states
        self.apply = apply
        self.calls: list = []
        self.parameters: dict = {}
        self.retry = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def set_request_parameter(self, key, value):
        self.parameters[key] = value

    def get_state_info(self, seq=None, retries=2):
        self.calls.append(("state", seq))
        return self.states.get(seq)

    def timestamp_to_sequence(self, timestamp, balanced_search=False, limit_by_oldest_available=False):
        self.calls.append(("sequence_for", timestamp))
        return None

    def apply_diffs_to_file(self, infile, outfile, start_id, max_size=None, set_replication_header=True, extra_headers=None, outformat=None, end_id=None):
        self.calls.append(("apply", start_id))
        assert not Path(outfile).exists(), "the writer refuses an existing output file"
        return self.apply(infile, outfile, start_id)


def make_source(tmp_path: Path, server, *, seed: Path | None, downloader=None, sleeps: list | None = None, **overrides) -> ExtractSource:
    kwargs = dict(
        extract_path=tmp_path / "extracts" / "colorado-cameras.osm.pbf",
        seed_path=seed,
        extract_url="https://extract.test/colorado-latest.osm.pbf",
        replication_url=REPLICATION_URL,
        user_agent="DeFlockMigration/test",
        backoff_seconds=5,
        pause_after_rate_limit_seconds=30,
        max_attempts=3,
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
        clock=lambda: NOW,
        server_factory=lambda url: server,
        downloader=downloader,
    )
    kwargs.update(overrides)
    return ExtractSource(**kwargs)


# ---- the tag filter --------------------------------------------------------------------------------------------------

def test_filter_matches_every_record_of_the_overpass_sample(overpass_fixture_payload):
    for element in overpass_fixture_payload["elements"]:
        assert matches_camera_filter(element.get("tags") or {}), element["id"]
    assert {"surveillance:type", "manufacturer", "operator", "brand", "camera:type", "disused:surveillance:type"} <= set(FILTER_KEYS)


@pytest.mark.parametrize("tags,expected", [
    ({"surveillance:type": "alpr"}, True),
    ({"surveillance:type": "ALPR;traffic"}, True),
    ({"camera:type": "ALPR/ANPR"}, True),
    ({"disused:surveillance:type": "ALPR"}, True),
    ({"removed:surveillance:type": "alpr"}, True),
    ({"operator": "Flock Safety"}, True),
    ({"brand": "FLOCK"}, True),
    ({"manufacturer": "flock safety"}, True),
    ({"surveillance:type": "camera"}, False),
    ({"man_made": "surveillance"}, False),
    ({"manufacturer": "Axis"}, False),
    ({}, False),
])
def test_filter_is_case_insensitive_and_leaves_other_surveillance_alone(tags, expected):
    assert matches_camera_filter(tags) is expected


# ---- extraction -------------------------------------------------------------------------------------------------------

def test_extraction_mirrors_the_overpass_element_shape(tmp_path):
    path = write_pbf(
        tmp_path / "tiny.osm.pbf", sequence=4945,
        nodes=[(1, *DENVER, CAMERA), (2, -105.0, 39.0, {}), (3, -105.001, 39.001, {}), (4, -105.1, 39.1, {"man_made": "surveillance", "surveillance:type": "camera"})],
        ways=[(10, [2, 3], {"surveillance:type": "ALPR"})],
        relations=[(20, [("w", 10, "outer"), ("n", 1, "")], {"operator": "Flock Safety"})],
    )
    extraction = extract_camera_elements(path)
    assert extraction.replication_sequence == 4945 and extraction.replication_url == REPLICATION_URL and extraction.data_timestamp == TS
    assert [(e["type"], e["id"]) for e in extraction.elements] == [("node", 1), ("way", 10), ("relation", 20)]
    node, way, relation = extraction.elements
    assert set(node) == {"type", "id", "version", "timestamp", "tags", "lat", "lon"}  # no contributor name or id
    assert node["timestamp"] == "2026-10-18T20:25:06Z" and node["version"] == 2 and node["tags"] == CAMERA
    assert (node["lon"], node["lat"]) == DENVER
    assert way["nodes"] == [2, 3] and len(way["geometry"]) == 2 and way["geometry"][0] == {"lat": 39.0, "lon": -105.0}
    assert relation["members"] == [{"type": "way", "ref": 10}, {"type": "node", "ref": 1}] and len(relation["geometry"]) == 3
    assert extraction.stats.node_count == 1 and extraction.stats.way_count == 1 and extraction.stats.relation_count == 1
    assert extraction.stats.key_filtered_objects == 4 and extraction.stats.unlocated_count == 0  # node 4 carries a filter key but is not ALPR
    records = normalize_elements(extraction.elements)
    assert [(r.source_key, r.geometry_quality) for r in records] == [("osm:node:1", "point"), ("osm:way:10", "representative_point"), ("osm:relation:20", "representative_point")]
    # operator=Flock is evidence, not ALPR typing: the same normalizer rule applies to elements from either source
    assert records[0].is_alpr and records[1].is_alpr and not records[2].is_alpr and not records[2].is_flock and records[2].operator == "Flock Safety"
    assert records[1].lat == pytest.approx(39.0005)


def test_extraction_counts_objects_without_a_usable_point(tmp_path):
    path = write_pbf(tmp_path / "tiny.osm.pbf", sequence=1, ways=[(10, [998, 999], {"surveillance:type": "ALPR"})])  # nodes not in the extract
    extraction = extract_camera_elements(path)
    assert extraction.elements == [] and extraction.stats.unlocated_count == 1


# ---- the source adapter --------------------------------------------------------------------------------------------------

def test_source_seeds_from_the_graph_extract_and_reports_up_to_date(tmp_path):
    seed = write_pbf(tmp_path / "pbf" / "colorado-latest.osm.pbf", sequence=4945, nodes=[(1, *DENVER, CAMERA), (2, *PUEBLO, CAMERA)])
    server = FakeServer({None: State(4945, TS)})
    source = make_source(tmp_path, server, seed=seed)
    result = source.fetch()
    assert result.ok and result.payload["osm3s"]["timestamp_osm_base"] == "2026-10-18T20:25:06Z"
    assert source.extract_path.exists() and not (tmp_path / "extracts" / "colorado-cameras.osm.pbf.part").exists()
    assert source.last_update.status == "up_to_date" and source.last_update.seeded_from == str(seed) and source.last_update.full_downloads == 0
    assert server.calls == [("state", None)]
    details = result.payload["source_details"]
    assert details["adapter"] == "geofabrik_extract" and details["replication_sequence"] == 4945 and details["extraction"]["nodes"] == 2
    assert [e["id"] for e in result.payload["elements"]] == [1, 2]
    assert source.endpoint == REPLICATION_URL and len(source.query_sha256) == 64
    again = source.fetch()  # the copy exists now; identical data hashes identically although the run details differ
    assert again.ok and again.data_sha256 == result.data_sha256 and source.last_update.seeded_from is None


def test_source_applies_change_files_in_order_and_replaces_the_file_atomically(tmp_path):
    extract = write_pbf(tmp_path / "extracts" / "colorado-cameras.osm.pbf", sequence=4945, nodes=[(1, *DENVER, CAMERA)])
    later = TS + dt.timedelta(days=2)

    def apply(infile, outfile, start):
        assert Path(infile) == extract and start == 4946
        write_pbf(Path(outfile), sequence=4947, timestamp=later, nodes=[(1, *DENVER, CAMERA), (5, *PUEBLO, CAMERA)])
        return (4947, 4947)

    server = FakeServer({None: State(4947, later), 4945: State(4945, TS)}, apply=apply)
    source = make_source(tmp_path, server, seed=None)
    result = source.fetch()
    assert result.ok and [e["id"] for e in result.payload["elements"]] == [1, 5]
    report = source.last_update
    assert (report.status, report.sequence_before, report.sequence_after, report.newest_sequence, report.diffs_applied) == ("updated", 4945, 4947, 4947, 2)
    assert report.timestamp_after == later.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert server.calls == [("state", None), ("state", 4945), ("apply", 4946)]
    assert not (tmp_path / "extracts" / "colorado-cameras.osm.updating.pbf").exists()


def test_unreachable_state_keeps_the_file_and_fails_politely(tmp_path):
    extract = write_pbf(tmp_path / "extracts" / "colorado-cameras.osm.pbf", sequence=4945, nodes=[(1, *DENVER, CAMERA)])
    before = extract.read_bytes()
    sleeps: list = []
    source = make_source(tmp_path, FakeServer({}), seed=None, sleeps=sleeps)
    result = source.fetch()
    assert not result.ok and "replication state unavailable after 3 attempt(s)" in result.error
    assert sleeps == [5, 10] and extract.read_bytes() == before


def test_missing_change_file_inside_the_retention_window_is_transient(tmp_path):
    write_pbf(tmp_path / "extracts" / "colorado-cameras.osm.pbf", sequence=4945, nodes=[(1, *DENVER, CAMERA)])
    downloads: list = []
    server = FakeServer({None: State(4950, TS)})  # the state file for 4945 is missing, five days behind
    source = make_source(tmp_path, server, seed=None, downloader=lambda *a, **k: downloads.append(a))
    result = source.fetch()
    assert not result.ok and "change file 4945 unavailable" in result.error and downloads == []
    assert ("apply", 4946) not in server.calls


def test_file_beyond_the_retention_window_is_reseeded_from_a_newer_seed(tmp_path):
    write_pbf(tmp_path / "extracts" / "colorado-cameras.osm.pbf", sequence=4800, nodes=[(1, *DENVER, CAMERA)])
    seed = write_pbf(tmp_path / "pbf" / "colorado-latest.osm.pbf", sequence=4945, nodes=[(1, *DENVER, CAMERA), (2, *PUEBLO, CAMERA)])
    downloads: list = []
    server = FakeServer({None: State(4945, TS), 4945: State(4945, TS)})
    source = make_source(tmp_path, server, seed=seed, downloader=lambda *a, **k: downloads.append(a))
    result = source.fetch()
    assert result.ok and [e["id"] for e in result.payload["elements"]] == [1, 2]
    report = source.last_update
    assert report.status == "up_to_date" and report.sequence_before == 4800 and report.sequence_after == 4945 and report.seeded_from == str(seed)
    assert downloads == [] and report.full_downloads == 0


def test_file_beyond_the_retention_window_without_a_seed_downloads_once(tmp_path):
    extract = write_pbf(tmp_path / "extracts" / "colorado-cameras.osm.pbf", sequence=4800, nodes=[(1, *DENVER, CAMERA)])
    downloads: list = []

    def download(url, dest_dir, filename, *, user_agent, force):
        downloads.append((url, Path(dest_dir) / filename, user_agent, force))
        write_pbf(Path(dest_dir) / filename, sequence=4945, nodes=[(1, *DENVER, CAMERA), (3, *PUEBLO, CAMERA)])
        return {"status": "downloaded"}

    server = FakeServer({None: State(4945, TS), 4945: State(4945, TS)})
    source = make_source(tmp_path, server, seed=None, downloader=download)
    result = source.fetch()
    assert result.ok and [e["id"] for e in result.payload["elements"]] == [1, 3]
    assert downloads == [("https://extract.test/colorado-latest.osm.pbf", extract, "DeFlockMigration/test", True)]
    assert source.last_update.full_downloads == 1 and source.last_update.status == "up_to_date"


def test_full_downloads_can_be_disabled(tmp_path):
    server = FakeServer({None: State(4945, TS)})
    source = make_source(tmp_path, server, seed=None, allow_full_download=False)
    result = source.fetch()
    assert not result.ok and "full downloads are disabled" in result.error


def test_rate_limit_answer_pauses_before_the_retry(tmp_path):
    import requests

    write_pbf(tmp_path / "extracts" / "colorado-cameras.osm.pbf", sequence=4945, nodes=[(1, *DENVER, CAMERA)])
    attempts: list = []

    def apply(infile, outfile, start):
        attempts.append(start)
        if len(attempts) == 1:
            raise requests.HTTPError("rate limited", response=types.SimpleNamespace(status_code=429))
        write_pbf(Path(outfile), sequence=4946, nodes=[(1, *DENVER, CAMERA)])
        return (4946, 4946)

    sleeps: list = []
    server = FakeServer({None: State(4946, TS), 4945: State(4945, TS)}, apply=apply)
    source = make_source(tmp_path, server, seed=None, sleeps=sleeps)
    result = source.fetch()
    assert result.ok and attempts == [4946, 4946] and sleeps == [30]
    assert source.last_update.status == "updated" and source.last_update.diffs_applied == 1


def test_default_replication_client_identifies_the_application_and_leaves_retries_to_the_adapter(tmp_path):
    source = make_source(tmp_path, None, seed=None, timeout_seconds=77, server_factory=None)
    server = source._default_server(REPLICATION_URL)  # noqa: SLF001 - the production client, not the fake
    assert server.baseurl == REPLICATION_URL + "/" and server.retry.total == 0
    assert server.extra_request_params["headers"] == {"User-Agent": "DeFlockMigration/test"} and server.extra_request_params["timeout"] == 77


def test_file_without_replication_information_cannot_be_updated(tmp_path):
    write_pbf(tmp_path / "extracts" / "colorado-cameras.osm.pbf", sequence=None, nodes=[(1, *DENVER, CAMERA)])
    source = make_source(tmp_path, FakeServer({None: State(4945, TS)}), seed=None, replication_url=None)
    result = source.fetch()
    assert not result.ok and "no replication information" in result.error


# ---- configuration and worker wiring -------------------------------------------------------------------------------------------

def test_camera_source_config_requires_the_fields_of_its_adapter():
    with pytest.raises(ValueError, match="extract block"):
        CameraSourceConfig(adapter="geofabrik_extract", query_bbox_swne=[36.7, -109.4, 41.3, -101.7])
    with pytest.raises(ValueError, match="endpoint and query_file"):
        CameraSourceConfig(adapter="overpass_bounded", query_bbox_swne=[36.7, -109.4, 41.3, -101.7])
    config = CameraSourceConfig(
        adapter="geofabrik_extract", query_bbox_swne=[36.7, -109.4, 41.3, -101.7],
        extract={"url": "https://extract.test/x.osm.pbf", "file": "x.osm.pbf", "replication_url": REPLICATION_URL},
    )
    assert config.extract.replication_url == REPLICATION_URL and config.endpoint is None


def test_missing_outline_file_is_a_configuration_error(project_root, tmp_path):
    import shutil

    root = tmp_path / "root"
    shutil.copytree(project_root / "configs", root / "configs")
    shutil.copytree(project_root / "data" / "boundaries", root / "data" / "boundaries")
    shutil.copytree(project_root / "data" / "raw" / "overpass", root / "data" / "raw" / "overpass", ignore=shutil.ignore_patterns("*.json"))
    (root / "data" / "boundaries" / "geofabrik_colorado_outline_v1.geojson").unlink()
    with pytest.raises(ConfigError, match="geofabrik_colorado_outline_v1"):
        load_app_config(Settings(app_env="test", project_root=root, database_url=None, geocoder_url=None))


def test_worker_builds_the_source_the_region_asks_for(app_config, settings, project_root):
    source = build_source(app_config, settings)
    assert isinstance(source, ExtractSource)
    assert source.extract_path == settings.camera_extract_dir / "colorado-cameras.osm.pbf" and source.endpoint == app_config.region.camera_source.extract.replication_url
    denver = load_app_config(Settings(app_env="test", project_root=project_root, database_url=None, geocoder_url=None, region_config="configs/regions/denver.yaml"))
    overpass = build_source(denver, settings)
    assert isinstance(overpass, OverpassSource) and overpass.endpoint == "https://overpass-api.de/api/interpreter" and overpass.id_prefix == "ovp"
    overpass.close()
