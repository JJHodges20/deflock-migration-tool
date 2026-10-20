"""Geofabrik extract download with checksum verification.

Used by the `osm-download` setup job (the routing graph's extract) and, since M10, by the extract-based camera
source when no seed file can be copied or the change files the local file needs are no longer published.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


def md5_file(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - Geofabrik publishes MD5 checksums
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_extract(url: str, dest_dir: Path, filename: str | None = None, *, user_agent: str, force: bool = False,
                     transport: httpx.BaseTransport | None = None) -> dict:
    """Download `url` into `dest_dir` (checksum verified against the published `.md5`); return the download record.

    An existing file whose checksum matches is kept (record status `present`) unless `force` is set. The download
    is written to a `.part` file and renamed only after the checksum matched, so a partial download never replaces
    a good file. Raises `DownloadError` on a checksum mismatch or an HTTP failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = filename or url.rsplit("/", 1)[-1]
    target = dest_dir / filename
    record_path = dest_dir / f"{filename}.download_record.json"
    headers = {"User-Agent": user_agent}

    with httpx.Client(headers=headers, timeout=httpx.Timeout(60.0, read=600.0), follow_redirects=True, transport=transport) as client:
        try:
            md5_resp = client.get(url + ".md5")
            md5_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise DownloadError(f"checksum file unavailable: {type(exc).__name__}") from exc
        expected = md5_resp.text.split()[0].strip().lower()
        if target.exists() and not force and md5_file(target) == expected:
            log.info("extract already present and checksum matches; skipping download")
            return {"status": "present", "file": str(target), "md5": expected}
        started = datetime.now(UTC)
        tmp = target.with_suffix(target.suffix + ".part")
        log.info("downloading extract")
        try:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as handle:
                    for chunk in resp.iter_bytes(1 << 20):
                        handle.write(chunk)
                last_modified = resp.headers.get("last-modified")
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise DownloadError(f"download failed: {type(exc).__name__}") from exc
        actual = md5_file(tmp)
        if actual != expected:
            tmp.unlink(missing_ok=True)
            raise DownloadError("checksum mismatch; download discarded")
        tmp.replace(target)
        sha256 = hashlib.sha256()
        with open(target, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                sha256.update(chunk)
        record = {
            "status": "downloaded",
            "url": url,
            "file": filename,
            "bytes": target.stat().st_size,
            "md5": actual,
            "sha256": sha256.hexdigest(),
            "source_last_modified": last_modified,
            "downloaded_at_start": started.isoformat().replace("+00:00", "Z"),
            "downloaded_at_end": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "license": "ODbL 1.0 (OpenStreetMap contributors), processed by Geofabrik GmbH",
        }
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        log.info("extract downloaded and verified (%s bytes)", record["bytes"])
    return record
