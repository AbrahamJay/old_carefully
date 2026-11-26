"""add agent_actions for llm audit

阶段五：只新增 Agent 审计表与索引，不改动既有业务表，可安全回退。
`thread_id` 预留给阶段七的对话会话，当前恒为空。

Revision ID: e5b8d2c41a90
Revises: d7c41e9b5a20
Create Date: 2026-11-26 18:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # alembic 渲染 JSONB(astext_type=Text()) 时需要显式导入
from sqlalchemy.dialects import postgresql

revision: str = "e5b8d2c41a90"
down_revision: str | None = "d7c41e9b5a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("thread_id", sa.String(length=40), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.String(length=40), nullable=False),
        sa.Column("step", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ok", nullable=False),
        sa.Column("model", sa.String(length=60), server_default="", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=40), server_default="", nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("payload_digest", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_actions_trace_id", "agent_actions", ["trace_id"])
    op.create_index("ix_agent_actions_created_at", "agent_actions", ["created_at"])
    op.create_index("ix_agent_actions_trace", "agent_actions", ["trace_id", "step"])
    op.create_index(
        "ix_agent_actions_user_created", "agent_actions", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_actions_user_created", table_name="agent_actions")
    op.drop_index("ix_agent_actions_trace", table_name="agent_actions")
    op.drop_index("ix_agent_actions_created_at", table_name="agent_actions")
    op.drop_index("ix_agent_actions_trace_id", table_name="agent_actions")
    op.drop_table("agent_actions")
