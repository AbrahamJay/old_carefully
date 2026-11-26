"""add staff availability, leaves, service skill, order status time

数据地基第一阶段：只新增列/表，不删改现有列，可安全回退。

Revision ID: b3f7c2a91d64
Revises: c4aec9c0e272
Create Date: 2026-11-26 09:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # alembic 渲染 JSONB(astext_type=Text()) 时需要显式导入
from sqlalchemy.dialects import postgresql

revision: str = 'b3f7c2a91d64'
down_revision: str | None = 'c4aec9c0e272'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 服务 code → 员工技能标签；后续管理员可在服务编辑页覆盖
_SKILL_BY_CODE = {
    'companion': '陪诊',
    'cleaning': '保洁',
    'renovation': '适老化评估',
    'errand': '代办',
    'meal': '助餐',
    'bath': '助浴',
    'repair': '水电维修',
    'medication': '用药提醒',
}


def upgrade() -> None:
    # 1. 员工可用性：老员工统一拿默认值，不阻塞派单
    op.add_column(
        'staff_profiles',
        sa.Column(
            'work_days',
            postgresql.JSONB(astext_type=Text()),
            server_default=sa.text("'[1,2,3,4,5,6,7]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        'staff_profiles',
        sa.Column('work_start_minute', sa.Integer(), server_default='480', nullable=False),
    )
    op.add_column(
        'staff_profiles',
        sa.Column('work_end_minute', sa.Integer(), server_default='1080', nullable=False),
    )
    op.add_column(
        'staff_profiles',
        sa.Column('daily_capacity', sa.Integer(), server_default='4', nullable=False),
    )
    op.add_column(
        'staff_profiles',
        sa.Column('accepting_orders', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )

    # 2. 请假：按天粒度
    op.create_table(
        'staff_leaves',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('staff_id', sa.Integer(), nullable=False),
        sa.Column('leave_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('staff_id', 'leave_date', name='uq_staff_leaves_staff_date'),
    )
    op.create_index('ix_staff_leaves_staff_id', 'staff_leaves', ['staff_id'], unique=False)

    # 3. 服务所需技能：按 code 回填，已有运营配置（非空）不覆盖
    op.add_column('services', sa.Column('required_skill', sa.String(length=30), nullable=True))
    for code, skill in _SKILL_BY_CODE.items():
        op.execute(
            sa.text(
                'UPDATE services SET required_skill = :skill '
                'WHERE code = :code AND required_skill IS NULL'
            ).bindparams(skill=skill, code=code)
        )

    # 4. 订单状态变更时间：先回填 updated_at，再收紧为 NOT NULL
    op.add_column(
        'orders',
        sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('UPDATE orders SET status_changed_at = updated_at WHERE status_changed_at IS NULL')
    op.alter_column(
        'orders',
        'status_changed_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text('now()'),
    )
    op.create_index(
        'ix_orders_status_status_changed_at',
        'orders',
        ['status', 'status_changed_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_orders_status_status_changed_at', table_name='orders')
    op.drop_column('orders', 'status_changed_at')

    op.drop_column('services', 'required_skill')

    op.drop_index('ix_staff_leaves_staff_id', table_name='staff_leaves')
    op.drop_table('staff_leaves')

    op.drop_column('staff_profiles', 'accepting_orders')
    op.drop_column('staff_profiles', 'daily_capacity')
    op.drop_column('staff_profiles', 'work_end_minute')
    op.drop_column('staff_profiles', 'work_start_minute')
    op.drop_column('staff_profiles', 'work_days')
