"""Setup job: download the Geofabrik regional extract once and verify its MD5. Idempotent."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from deflockmigration.core.logging import configure_logging
from deflockmigration.core.settings import Settings

log = logging.getLogger("deflockmigration.osm_download")


def md5_file(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - Geofabrik publishes MD5 checksums
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download a Geofabrik OSM extract with checksum verification")
    parser.add_argument("--url", required=True)
    parser.add_argument("--dest-dir", required=True)
    parser.add_argument("--filename", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)

    dest_dir = Path(args.dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = args.filename or args.url.rsplit("/", 1)[-1]
    target = dest_dir / filename
    record_path = dest_dir / f"{filename}.download_record.json"
    headers = {"User-Agent": settings.user_agent}

    with httpx.Client(headers=headers, timeout=httpx.Timeout(60.0, read=600.0), follow_redirects=True) as client:
        md5_resp = client.get(args.url + ".md5")
        md5_resp.raise_for_status()
        expected = md5_resp.text.split()[0].strip().lower()
        if target.exists() and not args.force and md5_file(target) == expected:
            log.info("extract already present and checksum matches; skipping download")
            return 0
        started = datetime.now(UTC)
        tmp = target.with_suffix(target.suffix + ".part")
        log.info("downloading extract")
        with client.stream("GET", args.url) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as handle:
                for chunk in resp.iter_bytes(1 << 20):
                    handle.write(chunk)
            last_modified = resp.headers.get("last-modified")
        actual = md5_file(tmp)
        if actual != expected:
            tmp.unlink(missing_ok=True)
            log.error("checksum mismatch; download discarded")
            return 1
        tmp.replace(target)
        sha256 = hashlib.sha256()
        with open(target, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                sha256.update(chunk)
        record = {
            "url": args.url,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
