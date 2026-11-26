"""add admin tasks for anomaly scan

异常巡检第四阶段：只新增表与索引，不删改现有列，可安全回退。

Revision ID: d7c41e9b5a20
Revises: b3f7c2a91d64
Create Date: 2026-11-26 15:40:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # alembic 渲染 JSONB(astext_type=Text()) 时需要显式导入
from sqlalchemy.dialects import postgresql

revision: str = "d7c41e9b5a20"
down_revision: str | None = "b3f7c2a91d64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=120), server_default="", nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by", sa.Integer(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=255), server_default="", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["handled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_admin_tasks_dedupe_key"),
    )
    op.create_index(
        "ix_admin_tasks_status_severity",
        "admin_tasks",
        ["status", "severity", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_tasks_order_type",
        "admin_tasks",
        ["order_id", "type", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_tasks_order_type", table_name="admin_tasks")
    op.drop_index("ix_admin_tasks_status_severity", table_name="admin_tasks")
    op.drop_table("admin_tasks")
