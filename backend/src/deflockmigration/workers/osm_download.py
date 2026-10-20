"""Setup job: download the Geofabrik regional extract once and verify its MD5. Idempotent.

The download itself lives in `deflockmigration.data_sources.geofabrik` so that the extract-based camera source
(M10) can reuse it without crossing the layer boundaries.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from deflockmigration.core.logging import configure_logging
from deflockmigration.core.settings import Settings
from deflockmigration.data_sources.geofabrik import DownloadError, download_extract, md5_file  # noqa: F401 - md5_file re-exported for scripts

log = logging.getLogger("deflockmigration.osm_download")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download a Geofabrik OSM extract with checksum verification")
    parser.add_argument("--url", required=True)
    parser.add_argument("--dest-dir", required=True)
    parser.add_argument("--filename", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)
    try:
        download_extract(args.url, Path(args.dest_dir), args.filename, user_agent=settings.user_agent, force=args.force)
    except DownloadError as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
