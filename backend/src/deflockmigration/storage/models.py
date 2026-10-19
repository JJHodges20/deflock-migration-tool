"""SQLAlchemy models: public camera snapshots and records only. No trip tables exist by design."""

from __future__ import annotations

import datetime as dt

from geoalchemy2 import Geography
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CameraSnapshot(Base):
    __tablename__ = "camera_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    region_id: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(300), nullable=False)
    query_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    query_bbox: Mapped[str] = mapped_column(String(120), nullable=False)
    generator: Mapped[str | None] = mapped_column(String(120))
    timestamp_osm_base: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    downloaded_at_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    downloaded_at_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    element_count: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alpr_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flock_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_manufacturer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_envelope_alpr_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_longer_mapped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_path: Mapped[str | None] = mapped_column(String(400))
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    license: Mapped[str] = mapped_column(String(120), nullable=False, default="ODbL 1.0 (OpenStreetMap contributors)")
    quality: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    promotion_state: Mapped[str] = mapped_column(String(20), nullable=False)  # staged | active | superseded | quarantined | rejected
    previous_active_snapshot_id: Mapped[str | None] = mapped_column(String(120))
    promoted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CameraRecord(Base):
    __tablename__ = "camera_records"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "source_key", name="uq_camera_records_snapshot_source"),
        Index("ix_camera_records_geom", "geom", postgresql_using="gist"),
        Index("ix_camera_records_snapshot", "snapshot_id"),
        Index("ix_camera_records_source_key", "source_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(120), ForeignKey("camera_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False)
    source_key: Mapped[str] = mapped_column(String(60), nullable=False)
    source_type: Mapped[str] = mapped_column(String(10), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_version: Mapped[int | None] = mapped_column(Integer)
    source_timestamp: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    geom = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False)
    geometry_quality: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_tags: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_alpr: Mapped[bool] = mapped_column(Boolean, nullable=False)
    alpr_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer_raw: Mapped[str | None] = mapped_column(String(120))
    manufacturer_normalized: Mapped[str | None] = mapped_column(String(80))
    is_flock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    operator: Mapped[str | None] = mapped_column(String(200))
    direction_raw: Mapped[str | None] = mapped_column(String(80))
    camera_direction_raw: Mapped[str | None] = mapped_column(String(80))
    direction_parsed_deg: Mapped[float | None] = mapped_column(Float)
    direction_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lifecycle_state: Mapped[str] = mapped_column(String(20), nullable=False)
    lifecycle_evidence: Mapped[str | None] = mapped_column(String(200))
    check_date: Mapped[str | None] = mapped_column(String(40))
    parse_warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    in_envelope: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    missing_since: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_snapshot_id: Mapped[str | None] = mapped_column(String(120))


class SnapshotDiff(Base):
    """What changed between the previous active snapshot and this one. Key lists are bounded; counts are exact."""

    __tablename__ = "snapshot_diffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(120), ForeignKey("camera_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False)
    previous_snapshot_id: Mapped[str | None] = mapped_column(String(120))
    added_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reappeared_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    carried_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    changed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CameraRoadAssociation(Base):
    """Cached nearest-road candidates for a camera record on one routing-graph version (roadmap section 7).
    Associations are graph-version specific and rebuilt after the graph changes."""

    __tablename__ = "camera_road_associations"
    __table_args__ = (
        UniqueConstraint("source_key", "graph_version", "radius_m", name="uq_camera_road_assoc"),
        Index("ix_camera_road_assoc_graph", "graph_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(60), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(160), nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    nearest_way_id: Mapped[int | None] = mapped_column(BigInteger)
    nearest_road_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    nearest_distance_m: Mapped[float | None] = mapped_column(Float)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candidates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)  # scheduled | manual | setup | review
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running | succeeded | failed | quarantined
    snapshot_id: Mapped[str | None] = mapped_column(String(120))
    http_status: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_count: Mapped[int | None] = mapped_column(Integer)
    changed_count: Mapped[int | None] = mapped_column(Integer)
    no_longer_present_count: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(String(400))
