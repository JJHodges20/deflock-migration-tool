"""Setup job: fetch the Protomaps basemap fonts and sprites at a pinned commit for self-hosting.

Fonts are Noto Sans under the SIL Open Font License; sprites derive from MIT-licensed icons.
The licence files are copied next to the assets.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from deflockmigration.core.logging import configure_logging
from deflockmigration.core.settings import Settings

log = logging.getLogger("deflockmigration.basemap_assets")
WANTED_PREFIXES = ("fonts/", "sprites/v4/", "README.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Protomaps basemap assets (fonts, sprites) at a pinned commit")
    parser.add_argument("--commit", required=True, help="protomaps/basemaps-assets commit SHA")
    parser.add_argument("--dest-dir", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)

    dest = Path(args.dest_dir)
    manifest_path = dest / "assets_manifest.json"
    if manifest_path.exists() and not args.force:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("commit") == args.commit and (dest / "fonts").exists() and (dest / "sprites" / "v4").exists():
            log.info("basemap assets already present at the pinned commit; skipping")
            return 0
    url = f"https://codeload.github.com/protomaps/basemaps-assets/zip/{args.commit}"
    log.info("downloading basemap assets archive")
    with httpx.Client(headers={"User-Agent": settings.user_agent}, timeout=httpx.Timeout(60.0, read=600.0), follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.content
    count = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            relative = member.filename.split("/", 1)[1] if "/" in member.filename else member.filename
            if not relative.startswith(WANTED_PREFIXES):
                continue
            out = dest / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, open(out, "wb") as handle:
                handle.write(src.read())
            count += 1
    manifest = {
        "source": "https://github.com/protomaps/basemaps-assets",
        "commit": args.commit,
        "files": count,
        "fonts_license": "SIL Open Font License (fonts/OFL.txt)",
        "sprites_license": "derived from MIT-licensed tangrams/icons",
        "downloaded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("extracted %s asset files", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
