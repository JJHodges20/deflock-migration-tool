"""inventory history, envelope flag, no-longer-mapped carry-over, snapshot review fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("camera_records", sa.Column("in_envelope", sa.Boolean, nullable=False, server_default=sa.true()))
    op.add_column("camera_records", sa.Column("missing_since", sa.DateTime(timezone=True)))
    op.add_column("camera_records", sa.Column("last_seen_snapshot_id", sa.String(120)))
    op.create_index("ix_camera_records_source_key", "camera_records", ["source_key"])

    op.add_column("camera_snapshots", sa.Column("in_envelope_alpr_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("camera_snapshots", sa.Column("no_longer_mapped_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("camera_snapshots", sa.Column("review_note", sa.Text))
    op.add_column("camera_snapshots", sa.Column("reviewed_at", sa.DateTime(timezone=True)))

    op.create_table(
        "snapshot_diffs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(120), sa.ForeignKey("camera_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_snapshot_id", sa.String(120)),
        sa.Column("added_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("changed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("missing_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reappeared_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("carried_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expired_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("added_keys", sa.JSON, nullable=False),
        sa.Column("changed", sa.JSON, nullable=False),
        sa.Column("missing_keys", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_snapshot_diffs_snapshot", "snapshot_diffs", ["snapshot_id"])


def downgrade() -> None:
    op.drop_table("snapshot_diffs")
    op.drop_column("camera_snapshots", "reviewed_at")
    op.drop_column("camera_snapshots", "review_note")
    op.drop_column("camera_snapshots", "no_longer_mapped_count")
    op.drop_column("camera_snapshots", "in_envelope_alpr_count")
    op.drop_index("ix_camera_records_source_key", table_name="camera_records")
    op.drop_column("camera_records", "last_seen_snapshot_id")
    op.drop_column("camera_records", "missing_since")
    op.drop_column("camera_records", "in_envelope")
