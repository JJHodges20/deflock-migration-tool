"""camera road association cache (graph-version specific)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_road_associations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_key", sa.String(60), nullable=False),
        sa.Column("graph_version", sa.String(160), nullable=False),
        sa.Column("radius_m", sa.Integer, nullable=False),
        sa.Column("method", sa.String(60), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nearest_way_id", sa.BigInteger),
        sa.Column("nearest_road_names", sa.JSON, nullable=False),
        sa.Column("nearest_distance_m", sa.Float),
        sa.Column("candidate_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ambiguous", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("candidates", sa.JSON, nullable=False),
        sa.UniqueConstraint("source_key", "graph_version", "radius_m", name="uq_camera_road_assoc"),
    )
    op.create_index("ix_camera_road_assoc_graph", "camera_road_associations", ["graph_version"])


def downgrade() -> None:
    op.drop_table("camera_road_associations")
