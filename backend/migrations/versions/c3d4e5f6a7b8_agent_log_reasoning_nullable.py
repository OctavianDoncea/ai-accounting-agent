"""agent_log reasoning nullable

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-05-22 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('agent_logs', 'reasoning', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column('agent_logs', 'reasoning', existing_type=sa.Text(), nullable=False)
