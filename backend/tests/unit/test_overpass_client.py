from __future__ import annotations

import json

import httpx

from deflockmigration.data_sources.overpass import OverpassClient

GOOD = {"version": 0.6, "generator": "Overpass API test", "osm3s": {"timestamp_osm_base": "2026-10-15T20:18:00Z"}, "elements": [{"type": "node", "id": 1, "lat": 39.7, "lon": -104.9, "tags": {"surveillance:type": "ALPR"}}]}


def _client(responses, sleeps):
    calls = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"].startswith("DeFlockMigration-test")
        assert b"data=" in request.content
        status, body, ctype = next(calls)
        return httpx.Response(status, content=body, headers={"content-type": ctype})

    return OverpassClient("http://overpass.test/api/interpreter", user_agent="DeFlockMigration-test/0", pause_after_rate_limit_seconds=30, max_attempts=3, backoff_seconds=5, transport=httpx.MockTransport(handler), sleep=sleeps.append)


def test_success_records_hash_and_count():
    sleeps: list[float] = []
    result = _client([(200, json.dumps(GOOD).encode(), "application/json")], sleeps).fetch("[out:json][bbox:1,2,3,4];node;out;")
    assert result.ok and result.element_count == 1 and result.attempts == 1 and result.sha256 and sleeps == []


def test_502_then_success_retries_with_backoff():
    sleeps: list[float] = []
    result = _client([(502, b"<html>Bad Gateway</html>", "text/html"), (200, json.dumps(GOOD).encode(), "application/json")], sleeps).fetch("q")
    assert result.ok and result.attempts == 2 and sleeps == [5]


def test_rate_limit_pauses_thirty_seconds():
    sleeps: list[float] = []
    result = _client([(429, b"too many", "text/plain"), (200, json.dumps(GOOD).encode(), "application/json")], sleeps).fetch("q")
    assert result.ok and sleeps == [30]


def test_html_challenge_page_is_a_failure_not_zero_cameras():
    result = _client([(200, b"<html>challenge</html>", "text/html")], []).fetch("q")
    assert not result.ok and result.payload is None and "non-JSON" in result.error


def test_remark_and_malformed_json_fail():
    bad_remark = dict(GOOD, remark="runtime error: Query timed out")
    assert not _client([(200, json.dumps(bad_remark).encode(), "application/json")], []).fetch("q").ok
    assert not _client([(200, b"{not json", "application/json")], []).fetch("q").ok


def test_gives_up_after_max_attempts():
    sleeps: list[float] = []
    result = _client([(503, b"", "text/plain")] * 3, sleeps).fetch("q")
    assert not result.ok and result.attempts == 3 and sleeps == [5, 10, 15]
