"""Policy-aware Overpass client for the fixed-region camera sync.

Rules implemented from the Overpass commons page and the OSM wiki (checked 2026-10-15):
identify the application, one request at a time, pause 30 s after 429/406, bounded retries,
treat HTML challenge pages and upstream remarks as failures, never derive the query from a trip.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    http_status: int | None
    body: bytes | None
    payload: dict | None
    started_at: dt.datetime
    finished_at: dt.datetime
    attempts: int
    error: str | None
    sha256: str | None
    data_sha256: str | None = None  # hash of the data part only, when the body also carries run-specific details (M10 extract source)

    @property
    def element_count(self) -> int | None:
        if self.payload is None:
            return None
        elements = self.payload.get("elements")
        return len(elements) if isinstance(elements, list) else None


class OverpassClient:
    def __init__(
        self,
        endpoint: str,
        *,
        user_agent: str,
        timeout_seconds: int = 180,
        pause_after_rate_limit_seconds: int = 30,
        max_attempts: int = 3,
        backoff_seconds: int = 5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], dt.datetime] | None = None,
    ):
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._pause = pause_after_rate_limit_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff = backoff_seconds
        self._sleep = sleep
        self._clock = clock or (lambda: dt.datetime.now(dt.UTC))
        self._client = httpx.Client(timeout=httpx.Timeout(timeout_seconds + 30, connect=15.0), transport=transport, headers={"User-Agent": user_agent})

    def close(self) -> None:
        self._client.close()

    def fetch(self, query_text: str) -> FetchResult:
        started = self._clock()
        attempts = 0
        last_error: str | None = None
        last_status: int | None = None
        while attempts < self._max_attempts:
            attempts += 1
            try:
                resp = self._client.post(self._endpoint, data={"data": query_text})
            except httpx.HTTPError as exc:
                last_error = f"transport error: {type(exc).__name__}"
                log.warning("overpass attempt %s failed: %s", attempts, last_error)
                self._sleep(self._backoff * attempts)
                continue
            last_status = resp.status_code
            if resp.status_code in (429, 406):
                last_error = f"rate limited (HTTP {resp.status_code})"
                log.warning("overpass attempt %s: %s; pausing %ss as the policy requires", attempts, last_error, self._pause)
                self._sleep(self._pause)
                continue
            if resp.status_code in (502, 503, 504):
                last_error = f"upstream unavailable (HTTP {resp.status_code})"
                log.warning("overpass attempt %s: %s", attempts, last_error)
                self._sleep(self._backoff * attempts)
                continue
            if resp.status_code != 200:
                last_error = f"unexpected HTTP {resp.status_code}"
                break
            body = resp.content
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type or body.lstrip()[:1] != b"{":
                last_error = "non-JSON response (possible challenge page)"
                break
            try:
                payload = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                last_error = "malformed JSON"
                break
            remark = payload.get("remark")
            if remark:
                last_error = f"upstream remark: {str(remark)[:160]}"
                break
            if not isinstance(payload.get("elements"), list):
                last_error = "payload has no elements list"
                break
            finished = self._clock()
            return FetchResult(True, resp.status_code, body, payload, started, finished, attempts, None, hashlib.sha256(body).hexdigest())
        finished = self._clock()
        return FetchResult(False, last_status, None, None, started, finished, attempts, last_error or "unknown failure", None)


class OverpassSource:
    """The Overpass client bound to the configured fixed query: the camera-source shape the sync pipeline consumes."""

    id_prefix = "ovp"
    source_name = "OpenStreetMap via Overpass API"

    def __init__(self, client: OverpassClient, query_text: str):
        self._client = client
        self._query_text = query_text

    @property
    def endpoint(self) -> str:
        return self._client._endpoint  # noqa: SLF001 - recorded for provenance

    @property
    def query_sha256(self) -> str:
        return hashlib.sha256(self._query_text.encode("utf-8")).hexdigest()

    def fetch(self) -> FetchResult:
        return self._client.fetch(self._query_text)

    def close(self) -> None:
        self._client.close()
