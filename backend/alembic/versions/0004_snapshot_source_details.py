"""snapshot source details (extract-based camera ingestion, M10)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Replication state, extraction statistics, and the filter version of a snapshot built from the regional extract.
    # Snapshots from the Overpass source keep NULL here.
    op.add_column("camera_snapshots", sa.Column("source_details", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("camera_snapshots", "source_details")
