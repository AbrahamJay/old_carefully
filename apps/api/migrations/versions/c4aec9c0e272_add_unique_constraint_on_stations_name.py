"""add unique constraint on stations.name

Revision ID: c4aec9c0e272
Revises: e70234af8edb
Create Date: 2026-11-25 13:53:10.231980

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # alembic 渲染 JSONB(astext_type=Text()) 时需要显式导入


revision: str = 'c4aec9c0e272'
down_revision: str | None = 'e70234af8edb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 若库里已存在重名站点，本迁移会失败（需先人工合并），这是有意为之。
    op.create_unique_constraint('uq_stations_name', 'stations', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_stations_name', 'stations', type_='unique')
