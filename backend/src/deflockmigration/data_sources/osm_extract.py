"""Camera source adapter: a regional OpenStreetMap extract kept current with the publisher's daily change files (M10).

Replaces the public Overpass dependency for the Colorado configuration (decision 0004). The adapter keeps one PBF
file in the worker's own volume, seeds it from the routing graph's extract when that is present (no second full
download), applies Geofabrik's daily `.osc.gz` change files with pyosmium's replication client, and hands the
filtered camera elements to the unchanged sync pipeline.

Politeness, the same rules as the Overpass client: an identifying User-Agent, one request at a time, a pause after
a rate-limit answer, bounded attempts, no endpoint rotation. A full extract download happens only when no usable
seed exists or the publisher no longer keeps the change files the local file needs (they are kept for about 100
days). The source is fixed by configuration and never derived from a trip.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from deflockmigration.data_sources.overpass import FetchResult
from deflockmigration.data_sources.extract_elements import FILTER_SPEC, FILTER_VERSION, Extraction, extract_camera_elements
from deflockmigration.data_sources.geofabrik import DownloadError, download_extract

log = logging.getLogger(__name__)
WIND_BACK = dt.timedelta(minutes=60)
ADAPTER = "geofabrik_extract"
MAX_DIFF_GAP = 90  # daily change files the publisher keeps (about 100 days); a smaller gap with a missing file is transient


@dataclass(frozen=True)
class UpdateReport:
    status: str  # up_to_date | updated | failed
    sequence_before: int | None = None
    sequence_after: int | None = None
    newest_sequence: int | None = None
    timestamp_after: str | None = None
    diffs_applied: int = 0
    requests: int = 0
    seeded_from: str | None = None
    full_downloads: int = 0
    error: str | None = None


class ExtractUnavailable(RuntimeError):
    pass


def _ts(value: dt.datetime | None) -> str | None:
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def _status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


class ExtractSource:
    """Fixed-region camera source backed by a local extract plus replication diffs."""

    id_prefix = "ext"
    source_name = "OpenStreetMap via Geofabrik extract and daily diffs"

    def __init__(
        self,
        *,
        extract_path: Path,
        seed_path: Path | None,
        extract_url: str,
        replication_url: str | None = None,
        user_agent: str,
        timeout_seconds: int = 120,
        pause_after_rate_limit_seconds: int = 30,
        max_attempts: int = 3,
        backoff_seconds: int = 5,
        max_diff_megabytes: int = 256,
        allow_full_download: bool = True,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], dt.datetime] | None = None,
        server_factory: Callable[[str], object] | None = None,
        downloader: Callable[..., dict] | None = None,
    ):
        self._extract_path = extract_path
        self._seed_path = seed_path
        self._extract_url = extract_url
        self._replication_url = replication_url
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._pause = pause_after_rate_limit_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff = backoff_seconds
        self._max_diff_kb = max(1, max_diff_megabytes) * 1024
        self._allow_full_download = allow_full_download
        self._sleep = sleep
        self._clock = clock or (lambda: dt.datetime.now(dt.UTC))
        self._server_factory = server_factory or self._default_server
        self._downloader = downloader or download_extract
        self._header_url: str | None = None
        self.last_update: UpdateReport | None = None
        self.last_extraction: Extraction | None = None

    # -- descriptor -------------------------------------------------------------------------------------------------
    @property
    def endpoint(self) -> str:
        return self._replication_url or self._header_url or self._extract_url

    @property
    def query_sha256(self) -> str:
        return hashlib.sha256(FILTER_SPEC.encode("utf-8")).hexdigest()

    @property
    def extract_path(self) -> Path:
        return self._extract_path

    def close(self) -> None:
        return None

    # -- replication client --------------------------------------------------------------------------------------------
    def _default_server(self, url: str):
        from osmium.replication.server import ReplicationServer
        from urllib3.util import Retry

        server = ReplicationServer(url)
        server.retry = Retry(total=0)  # attempts and pauses are this adapter's responsibility, so the disclosed policy is the real one
        server.set_request_parameter("headers", {"User-Agent": self._user_agent})
        server.set_request_parameter("timeout", self._timeout)
        return server

    # -- the fetch the sync pipeline sees ------------------------------------------------------------------------------
    def fetch(self) -> FetchResult:
        started = self._clock()
        try:
            seeded_from, full_downloads = self._ensure_seed()
            report = self._update(seeded_from, full_downloads)
            self.last_update = report
            if report.status == "failed":
                log.warning("extract update failed: %s", report.error)
                return FetchResult(False, None, None, None, started, self._clock(), report.requests, report.error, None)
            extraction = extract_camera_elements(self._extract_path)
            self.last_extraction = extraction
            payload = self._payload(extraction, report)
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            data = json.dumps({"osm3s": payload["osm3s"], "elements": payload["elements"]}, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return FetchResult(True, None, body, payload, started, self._clock(), report.requests, None,
                               hashlib.sha256(body).hexdigest(), data_sha256=hashlib.sha256(data).hexdigest())
        except (DownloadError, ExtractUnavailable) as exc:
            log.warning("extract source unavailable: %s", exc)
            return FetchResult(False, None, None, None, started, self._clock(), 0, str(exc)[:200], None)
        except Exception as exc:  # noqa: BLE001 - a source failure keeps the last good snapshot; the job row records it
            log.exception("extract source failed")
            return FetchResult(False, None, None, None, started, self._clock(), 0, f"extract source error: {type(exc).__name__}", None)

    def _payload(self, extraction: Extraction, report: UpdateReport) -> dict:
        from osmium.version import pyosmium_release

        return {
            "version": 0.6,
            "generator": f"DeFlockMigration extract adapter ({FILTER_VERSION}; pyosmium {pyosmium_release})",
            "osm3s": {
                "timestamp_osm_base": _ts(extraction.data_timestamp),
                "copyright": "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL.",
            },
            "source_details": {
                "adapter": ADAPTER,
                "extract_file": self._extract_path.name,
                "extract_bytes": self._extract_path.stat().st_size,
                "extract_url": self._extract_url,
                "replication_url": extraction.replication_url,
                "replication_sequence": extraction.replication_sequence,
                "update": asdict(report),
                "extraction": extraction.stats.as_dict(),
                "filter_version": FILTER_VERSION,
                "filter_spec": FILTER_SPEC,
                "pyosmium_version": pyosmium_release,
            },
            "elements": extraction.elements,
        }

    # -- seed ------------------------------------------------------------------------------------------------------------
    def _ensure_seed(self) -> tuple[str | None, int]:
        if self._extract_path.exists():
            return None, 0
        self._extract_path.parent.mkdir(parents=True, exist_ok=True)
        if self._seed_path is not None and self._seed_path.exists():
            self._copy_seed()
            return str(self._seed_path), 0
        if not self._allow_full_download:
            raise ExtractUnavailable("no extract file and no seed to copy; full downloads are disabled")
        self._download_fresh()
        return self._extract_url, 1

    def _copy_seed(self) -> None:
        tmp = self._extract_path.with_name(self._extract_path.name + ".part")
        shutil.copyfile(self._seed_path, tmp)
        os.replace(tmp, self._extract_path)
        log.info("seeded the camera extract from %s (no download)", self._seed_path)

    def _download_fresh(self) -> None:
        log.info("downloading a fresh extract (checksum verified)")
        self._downloader(self._extract_url, self._extract_path.parent, self._extract_path.name, user_agent=self._user_agent, force=True)

    # -- update ----------------------------------------------------------------------------------------------------------
    def _update(self, seeded_from: str | None, full_downloads: int) -> UpdateReport:
        from osmium.replication.utils import get_replication_header

        header = get_replication_header(str(self._extract_path))
        self._header_url = header.url
        url = self._replication_url or header.url
        if not url:
            return UpdateReport("failed", header.sequence, header.sequence, None, _ts(header.timestamp), 0, 0, seeded_from, full_downloads,
                                error="the extract carries no replication information; change files cannot be applied")
        requests_made = 0
        diffs_applied = 0
        newest: int | None = None
        with self._server_factory(url) as server:
            state, used = self._state_with_attempts(server, None)
            requests_made += used
            if state is None:
                return UpdateReport("failed", header.sequence, header.sequence, None, _ts(header.timestamp), 0, requests_made, seeded_from, full_downloads,
                                    error=f"replication state unavailable after {used} attempt(s); last known good snapshot retained")
            newest = state.sequence
            if header.sequence is not None:
                if header.sequence >= state.sequence:
                    return UpdateReport("up_to_date", header.sequence, header.sequence, newest, _ts(header.timestamp), 0, requests_made, seeded_from, full_downloads)
                available, used = self._state_with_attempts(server, header.sequence)
                requests_made += used
                if available is None:
                    if state.sequence - header.sequence < MAX_DIFF_GAP:
                        # The publisher keeps change files for about 100 days; a missing one inside that window is a
                        # transient failure, not a reason to download a whole extract.
                        return UpdateReport("failed", header.sequence, header.sequence, newest, _ts(header.timestamp), 0, requests_made, seeded_from, full_downloads,
                                            error=f"change file {header.sequence} unavailable after {used} attempt(s); retrying at the next interval")
                    return self._reseed_and_retry(seeded_from, full_downloads, requests_made, f"change file {header.sequence} is no longer published")
                start = header.sequence + 1
            else:
                if header.timestamp is None:
                    return UpdateReport("failed", None, None, newest, None, 0, requests_made, seeded_from, full_downloads,
                                        error="the extract carries neither a sequence number nor a data timestamp")
                start = server.timestamp_to_sequence(header.timestamp - WIND_BACK, limit_by_oldest_available=True)
                requests_made += 1
                if start is None:
                    return self._reseed_and_retry(seeded_from, full_downloads, requests_made, "no change file covers the extract's data timestamp any more")
            while True:
                tmp = self._extract_path.with_name(f"{self._extract_path.stem}.updating{self._extract_path.suffix}")  # keeps the .pbf suffix the writers detect
                tmp.unlink(missing_ok=True)
                result, used = self._apply_with_attempts(server, start, tmp)
                requests_made += used
                if result is None:
                    break
                last, newest = result
                os.replace(tmp, self._extract_path)
                diffs_applied += last - start + 1
                log.info("applied change files %s to %s (newest published %s)", start, last, newest)
                start = last + 1
                if last >= newest:
                    break
        after = get_replication_header(str(self._extract_path))
        return UpdateReport("updated" if diffs_applied else "up_to_date", header.sequence, after.sequence, newest, _ts(after.timestamp),
                            diffs_applied, requests_made, seeded_from, full_downloads)

    def _reseed_and_retry(self, seeded_from: str | None, full_downloads: int, requests_made: int, reason: str) -> UpdateReport:
        from osmium.replication.utils import get_replication_header

        current = get_replication_header(str(self._extract_path)).sequence
        if self._seed_path is not None and self._seed_path.exists():
            seed_sequence = get_replication_header(str(self._seed_path)).sequence
            if seed_sequence is not None and (current is None or seed_sequence > current):
                log.warning("%s; re-seeding from %s", reason, self._seed_path)
                self._copy_seed()
                report = self._update(str(self._seed_path), full_downloads)
                return UpdateReport(report.status, current, report.sequence_after, report.newest_sequence, report.timestamp_after, report.diffs_applied,
                                    report.requests + requests_made, str(self._seed_path), report.full_downloads, report.error)
        if self._allow_full_download and full_downloads == 0:
            log.warning("%s; downloading a fresh extract once", reason)
            self._download_fresh()
            report = self._update(seeded_from, 1)
            return UpdateReport(report.status, current, report.sequence_after, report.newest_sequence, report.timestamp_after, report.diffs_applied,
                                report.requests + requests_made, report.seeded_from, 1, report.error)
        return UpdateReport("failed", current, current, None, None, 0, requests_made, seeded_from, full_downloads,
                            error=f"{reason}; a fresh extract is required and full downloads are exhausted or disabled")

    def _state_with_attempts(self, server, sequence: int | None):
        attempts = 0
        while attempts < self._max_attempts:
            attempts += 1
            state = server.get_state_info(sequence)
            if state is not None:
                return state, attempts
            if attempts < self._max_attempts:
                self._sleep(self._backoff * attempts)
        return None, attempts

    def _apply_with_attempts(self, server, start: int, tmp: Path):
        import requests

        attempts = 0
        while True:
            attempts += 1
            try:
                result = server.apply_diffs_to_file(str(self._extract_path), str(tmp), start, max_size=self._max_diff_kb,
                                                    extra_headers={"generator": f"DeFlockMigration camera-sync ({FILTER_VERSION})"}, outformat="pbf")
            except requests.RequestException as exc:
                tmp.unlink(missing_ok=True)
                status = _status_code(exc)
                if status in (429, 503) and attempts < self._max_attempts:
                    log.warning("replication server answered HTTP %s; pausing %ss as the policy requires", status, self._pause)
                    self._sleep(self._pause)
                    continue
                if attempts < self._max_attempts:
                    log.warning("change file download failed (%s); retrying", type(exc).__name__)
                    self._sleep(self._backoff * attempts)
                    continue
                raise ExtractUnavailable(f"change file download failed after {attempts} attempt(s): {type(exc).__name__}") from exc
            # requests made: one state read, the change files, and one state read for the header
            if result is None:
                return None, attempts
            return result, attempts + (result[0] - start + 1) + 1
