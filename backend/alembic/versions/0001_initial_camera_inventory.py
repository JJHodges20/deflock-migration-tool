"""initial camera inventory tables

Revision ID: 0001
Revises:
Create Date: 2026-10-15
"""
from __future__ import annotations

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "camera_snapshots",
        sa.Column("snapshot_id", sa.String(120), primary_key=True),
        sa.Column("region_id", sa.String(40), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("endpoint", sa.String(300), nullable=False),
        sa.Column("query_sha256", sa.String(64), nullable=False),
        sa.Column("query_bbox", sa.String(120), nullable=False),
        sa.Column("generator", sa.String(120)),
        sa.Column("timestamp_osm_base", sa.DateTime(timezone=True)),
        sa.Column("downloaded_at_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("element_count", sa.Integer, nullable=False),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("alpr_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("flock_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unknown_manufacturer_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("raw_bytes", sa.BigInteger, nullable=False),
        sa.Column("raw_path", sa.String(400)),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("license", sa.String(120), nullable=False, server_default="ODbL 1.0 (OpenStreetMap contributors)"),
        sa.Column("quality", sa.JSON, nullable=False),
        sa.Column("promotion_state", sa.String(20), nullable=False),
        sa.Column("previous_active_snapshot_id", sa.String(120)),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_camera_snapshots_region_state", "camera_snapshots", ["region_id", "promotion_state"])
    op.create_table(
        "camera_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(120), sa.ForeignKey("camera_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(60), nullable=False),
        sa.Column("source_type", sa.String(10), nullable=False),
        sa.Column("source_id", sa.BigInteger, nullable=False),
        sa.Column("source_version", sa.Integer),
        sa.Column("source_timestamp", sa.DateTime(timezone=True)),
        sa.Column("geom", geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("geometry_quality", sa.String(30), nullable=False),
        sa.Column("raw_tags", sa.JSON, nullable=False),
        sa.Column("is_alpr", sa.Boolean, nullable=False),
        sa.Column("alpr_evidence", sa.Text, nullable=False),
        sa.Column("manufacturer_raw", sa.String(120)),
        sa.Column("manufacturer_normalized", sa.String(80)),
        sa.Column("is_flock", sa.Boolean, nullable=False),
        sa.Column("operator", sa.String(200)),
        sa.Column("direction_raw", sa.String(80)),
        sa.Column("camera_direction_raw", sa.String(80)),
        sa.Column("direction_parsed_deg", sa.Float),
        sa.Column("direction_conflict", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("lifecycle_state", sa.String(20), nullable=False),
        sa.Column("lifecycle_evidence", sa.String(200)),
        sa.Column("check_date", sa.String(40)),
        sa.Column("parse_warnings", sa.JSON, nullable=False),
        sa.UniqueConstraint("snapshot_id", "source_key", name="uq_camera_records_snapshot_source"),
    )
    op.create_index("ix_camera_records_snapshot", "camera_records", ["snapshot_id"])
    op.execute("CREATE INDEX ix_camera_records_geom ON camera_records USING GIST (geom)")
    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("region_id", sa.String(40), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot_id", sa.String(120)),
        sa.Column("http_status", sa.Integer),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("added_count", sa.Integer),
        sa.Column("changed_count", sa.Integer),
        sa.Column("no_longer_present_count", sa.Integer),
        sa.Column("message", sa.String(400)),
    )
    op.create_index("ix_sync_jobs_region_started", "sync_jobs", ["region_id", "started_at"])


def downgrade() -> None:
    op.drop_table("sync_jobs")
    op.drop_table("camera_records")
    op.drop_table("camera_snapshots")
